"""
scanner.py
----------
YouTube 直播检测逻辑

公共接口
--------
SCAN_STATE_STORE                全局扫描状态存储（由 api.py 通过 get_snapshot() 读取）
check_live_sync(...)            同步检测单个频道（在线程池中调用）
normalize_channel_live_url(q)   将各种频道标识统一转为 /live URL
start_scan_task()               asyncio 协程，批量扫描 channels.csv
EXECUTOR                        供 api.py 共享的线程池
"""

import asyncio
import logging
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import requests
from yt_dlp import YoutubeDL

from ..cache import avatar_cache as _ac
from ..utils.channel_csv_reader import read_all_csv_rows_in_dir, resolve_channels_dir
from ..models.scan_state_store import ScanStateStore
from ..services import youtube_probe as _yt_probe
from ..services.scanner_utils import classify_ytdlp_exception, normalize_channel_live_url  # noqa: F401 (re-export)
from ..websocket.manager import broadcast_scan_status

# ── 可调参数（集中管理） ─────────────────────────────────────────────────
_MAX_WORKERS              = 60     # ThreadPoolExecutor 线程数
_BATCH_MIN                = 5      # 批次最小大小
_BATCH_MAX                = 40     # 批次最大大小
_JITTER_MIN               = 0.5    # HEAD 请求抖动下限（秒）
_JITTER_MAX               = 2.0    # HEAD 请求抖动上限（秒）

EXECUTOR         = ThreadPoolExecutor(max_workers=_MAX_WORKERS)
SCAN_STATE_STORE = ScanStateStore()
_MONITOR_INTERVAL_SEC = 300
_MONITOR_TOKEN = 0

# R2: asyncio.Event — 新扫描启动时 set，monitor 任务立即退出
_monitor_cancel_event: asyncio.Event | None = None

_HEAD_TIMEOUT = 4
_YDL_TIMEOUT  = 8

# R3: 429 退避机制
_rate_limit_until: float = 0.0
_RATE_LIMIT_COOLDOWN_SEC = 30

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1F\x7F]")
_HEAD_HEADERS     = {"User-Agent": "Mozilla/5.0"}

# 连接复用：全局 requests.Session（TCP 连接池）
_head_session = requests.Session()
_head_session.headers.update(_HEAD_HEADERS)

_logger: logging.Logger | None = None
_app_dir_fn = None


def init(logger: logging.Logger, app_dir_fn) -> None:
    """由 main.py 在启动时注入依赖。"""
    global _logger, _app_dir_fn
    _logger     = logger
    _app_dir_fn = app_dir_fn


def _log(level: str, msg: str, *args):
    if _logger:
        getattr(_logger, level)(msg, *args)


# ── R3: 429 退避辅助 ─────────────────────────────────────────────────────────

def _check_rate_limit_delay() -> None:
    """如果处于 429 冷却期，额外等待剩余时间。"""
    now = time.time()
    if now < _rate_limit_until:
        extra = _rate_limit_until - now
        _log("warning", "rate-limit cooldown: sleeping %.1fs", extra)
        time.sleep(extra)


def _trigger_rate_limit() -> None:
    """检测到 429 时触发全局冷却。"""
    global _rate_limit_until
    _rate_limit_until = time.time() + _RATE_LIMIT_COOLDOWN_SEC
    _log("warning", "YouTube rate limit detected, entering %ds cooldown",
         _RATE_LIMIT_COOLDOWN_SEC)


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def _extract_handle_mark(value: str) -> Optional[str]:
    if not value:
        return None
    m = re.search(r"/@([^/?#]+)", value)
    if m:
        return f"@{m.group(1)}"
    m = re.search(r"@([A-Za-z0-9._-]{3,})", value)
    if m:
        return f"@{m.group(1)}"
    return None


def extract_handle_mark(value: str) -> Optional[str]:
    """公开的 handle 提取函数。"""
    return _extract_handle_mark(value)


def _clean_display_name(raw: Optional[str], fallback_mark: str) -> str:
    s = (raw or "").strip()
    if s:
        s = _CONTROL_CHARS_RE.sub("", s)
        s = s.replace("\uFFFD", "")
        s = " ".join(s.split())
        readable = sum(
            1 for ch in s
            if ch.isalnum() or ("\u4e00" <= ch <= "\u9fff") or ("\u3040" <= ch <= "\u30ff")
        )
        if len(s) >= 2 and readable >= 2:
            return s
    return fallback_mark


# ── 预筛（快速 HTTP 判断）────────────────────────────────────────────────────

def _is_live_head(url: str) -> bool:
    """
    GET 请求，跟随重定向。
    落在 /watch?v= 或仍含 /live -> 可能在播，返回 True。
    使用 requests.Session 实现 TCP 连接池复用 + 随机抖动防风控。
    """
    _check_rate_limit_delay()  # R3: 429 冷却期额外等待
    time.sleep(random.uniform(_JITTER_MIN, _JITTER_MAX))
    try:
        resp = _head_session.get(url, timeout=_HEAD_TIMEOUT, allow_redirects=True)
        if resp.status_code == 429:
            _trigger_rate_limit()
            _log("warning", "HEAD got 429 for %s", url)
            return False
        final_url = resp.url
        return "watch?v=" in final_url or "/live" in final_url
    except requests.RequestException as exc:
        _log("warning", "HEAD request failed for %s: %s", url, exc)
        return False
    except Exception as exc:
        _log("warning", "HEAD unexpected error for %s: %s", url, exc)
        return False


# ── 核心检测 ──────────────────────────────────────────────────────────────────

def check_live_sync(
    url: str,
    channel_id: str,
    name_raw: Optional[str],
    handle_mark: Optional[str],
) -> Optional[dict]:
    """
    同步检测单个频道直播状态，在 EXECUTOR 线程池中运行。
    返回直播信息字典，或 None（未直播）。
    """
    if not _is_live_head(url):
        return None

    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "playlist_items": "0",
        "socket_timeout": _YDL_TIMEOUT,
    }
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info and info.get("is_live"):
                fallback_mark   = handle_mark or (f"@{channel_id}" if channel_id else "@unknown")
                real_channel_id = channel_id or info.get("channel_id") or info.get("uploader_id") or ""
                raw_title = info.get("title") or ""
                clean_title = re.sub(
                    r'[\s　]*[（(【]\s*\d{4}[-/年]\d{1,2}[-/月]\d{1,2}'
                    r'(?:[日\s　]*\d{1,2}[:/]\d{2}(?:[:/]\d{2})?)?\s*[）)】]\s*$',
                    "",
                    raw_title,
                ).strip()
                return {
                    "id":     real_channel_id or info.get("id"),
                    "name":   _clean_display_name(name_raw, fallback_mark),
                    "title":  clean_title,
                    "url":    f"https://www.youtube.com/watch?v={info.get('id')}",
                    "channel_live_url": url,
                }
    except Exception as e:
        state = classify_ytdlp_exception(e)
        if state == "rate_limited":
            _trigger_rate_limit()
            _log("warning", "yt-dlp rate limited on %s (channel_id=%s)", url, channel_id)
        elif state == "offline":
            _log("debug", "channel offline: %s (channel_id=%s)", url, channel_id)
        else:
            _log("warning", "yt-dlp extract failed for %s (state=%s): %s", url, state, e)
    return None


def fetch_avatar_background(item: dict) -> None:
    """后台预热头像缓存。avatar 是派生字段，由 API 层在响应时注入，此处只写缓存。"""
    try:
        channel_id = (item.get("id") or "").strip()
        if not channel_id:
            return
        if _ac.get_cached_avatar(channel_id):
            return
        channel_live_url = (item.get("channel_live_url") or "").strip()
        if not channel_live_url:
            return
        _ac.fetch_channel_avatar(channel_live_url, channel_id)
    except Exception as exc:
        _log("warning", "fetch_avatar_background failed for channel_id=%s: %s",
             item.get("id", "?"), exc)


# ── 监测 ─────────────────────────────────────────────────────
# classify_ytdlp_exception 定义在 scanner_utils.py，此处通过模块级 import 重导出


def _recheck_live_ytdlp(item: dict) -> dict | None:
    """
    用 yt-dlp 直接检测 channel_live_url 主页是否仍在直播。

    返回规则：
      is_live=True                          -> 保留卡片
      is_live=False 或 info 为空            -> 移除卡片
      offline / ended / upcoming / terminated -> 明确下播，移除卡片
      js_error / rate_limited / unknown 异常 -> 保守保留
    """
    url = (item.get("channel_live_url") or item.get("url") or "").strip()
    if not url:
        return item  # 无链接，保守保留

    _check_rate_limit_delay()  # R3: 429 冷却期额外等待

    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "socket_timeout": _YDL_TIMEOUT,
    }

    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)

        if info and info.get("is_live"):
            return item

        return None

    except Exception as e:
        state = classify_ytdlp_exception(e)
        _log("debug", "recheck [%s] state=%s | %s", url, state, e)

        # 明确下播：移除卡片
        if state in ("offline", "ended", "upcoming", "terminated"):
            return None

        # R3: 429 限速 — 触发冷却，保守保留
        if state == "rate_limited":
            _trigger_rate_limit()
            return item

        # 环境问题 / 未知异常：保守保留
        return item


def _monitor_recheck_sync(item: dict) -> dict | None:
    """监控复检入口，供线程池调用。"""
    return _recheck_live_ytdlp(item)


# ── 频道标识规范化 ────────────────────────────────────────────────────────────
# normalize_channel_live_url 定义在 scanner_utils.py，此处通过模块级 import 重导出


# ── CSV 批量扫描协程 ──────────────────────────────────────────────────────────

async def start_scan_task() -> None:
    """从应用目录下全部 CSV 批量扫描直播，更新 SCAN_STATE。"""
    global _MONITOR_TOKEN, _monitor_cancel_event

    if not _yt_probe.can_run_youtube_workflows():
        _log("warning", "Scan blocked: YouTube network unavailable")
        SCAN_STATE_STORE.reset_for_new_scan()
        SCAN_STATE_STORE.set_running(False)
        SCAN_STATE_STORE.set_monitoring(False)
        await broadcast_scan_status()
        return
    app_dir = _app_dir_fn()
    channels_dir = resolve_channels_dir(app_dir)
    if not channels_dir:
        _log("warning", "Channels directory not found (app_dir=%s)", app_dir)
        SCAN_STATE_STORE.set_running(False)
        await broadcast_scan_status()
        return

    channels = _load_channels_csv(channels_dir)
    if not channels:
        SCAN_STATE_STORE.set_running(False)
        await broadcast_scan_status()
        return

    _MONITOR_TOKEN += 1
    # R2: 唤醒正在 sleep 的旧 monitor，使其立即退出
    if _monitor_cancel_event is not None:
        _monitor_cancel_event.set()
    SCAN_STATE_STORE.reset_for_new_scan()
    SCAN_STATE_STORE.set_total(len(channels))
    await broadcast_scan_status()

    loop = asyncio.get_running_loop()

    total_channels = len(channels)
    batch_size = min(max(total_channels, _BATCH_MIN), _BATCH_MAX)
    _log("info", "Scan started: %d channels, batch_size=%d", total_channels, batch_size)

    try:
        for i in range(0, len(channels), batch_size):
            batch = channels[i : i + batch_size]
            tasks = []
            for c in batch:
                cid         = c.get("id", "").strip()
                raw_url     = (c.get("url") or c.get("URL") or "").strip()
                name_raw    = c.get("title") or c.get("name") or ""
                handle_mark = _extract_handle_mark(raw_url) or _extract_handle_mark(name_raw)

                target_url = None
                if cid:
                    if cid.startswith("UC"):
                        target_url = f"https://www.youtube.com/channel/{cid}/live"
                    elif cid.startswith("http"):
                        target_url = cid

                if target_url:
                    tasks.append(
                        loop.run_in_executor(
                            EXECUTOR, check_live_sync, target_url, cid, name_raw, handle_mark
                        )
                    )

            if tasks:
                results      = await asyncio.gather(*tasks)
                live_results = [r for r in results if r]
                SCAN_STATE_STORE.add_results(live_results)
                for item in live_results:
                    loop.run_in_executor(EXECUTOR, fetch_avatar_background, item)

            SCAN_STATE_STORE.add_progress(len(batch))
            await broadcast_scan_status()
    finally:
        SCAN_STATE_STORE.set_running(False)
        await broadcast_scan_status()
        asyncio.create_task(start_live_monitor_task(_MONITOR_TOKEN))


async def start_live_monitor_task(token: int) -> None:
    """
    扫描结束后每 5 分钟复检一轮在线卡片。
    并发数限制为 3，直接调用 yt-dlp 检测 /live 主页。

    R2: 使用 asyncio.Event 实现新扫描时立即退出。
    将 asyncio.sleep(interval) 替换为
    asyncio.wait_for(event.wait(), timeout=interval)，
    event 被 set 时立即唤醒并退出，不再等待整个间隔。
    """
    global _monitor_cancel_event

    if token != _MONITOR_TOKEN:
        return

    # 为本轮 monitor 创建全新的 Event
    _monitor_cancel_event = asyncio.Event()
    event = _monitor_cancel_event

    SCAN_STATE_STORE.set_monitoring(True)
    await broadcast_scan_status()
    loop = asyncio.get_running_loop()
    semaphore = asyncio.Semaphore(3)

    async def _recheck_with_limit(item: dict) -> dict | None:
        async with semaphore:
            return await loop.run_in_executor(
                EXECUTOR, _monitor_recheck_sync, item
            )

    # 扫描结束后立即补抓空头像，不必等首轮 5 分钟监测
    for item in list(SCAN_STATE_STORE.get_snapshot()["results"]):
        cid = (item.get("id") or "").strip()
        if cid and not _ac.get_cached_avatar(cid):
            loop.run_in_executor(EXECUTOR, fetch_avatar_background, item)

    try:
        # R2: 等待间隔，但新扫描启动时 event 被 set，立即唤醒退出
        try:
            await asyncio.wait_for(event.wait(), timeout=_MONITOR_INTERVAL_SEC)
            _log("info", "monitor cancelled by new scan before first recheck (token=%d)", token)
            return
        except asyncio.TimeoutError:
            pass  # 正常超时 -> 继续复检

        while token == _MONITOR_TOKEN and not SCAN_STATE_STORE.is_running:
            current_items = list(SCAN_STATE_STORE.get_snapshot()["results"])
            if not current_items:
                break

            tasks     = [_recheck_with_limit(item) for item in current_items]
            refreshed = await asyncio.gather(*tasks)

            live_results = [r for r in refreshed if r]
            SCAN_STATE_STORE.replace_results(live_results)

            await broadcast_scan_status()

            if not live_results:
                break

            for item in live_results:
                if not _ac.get_cached_avatar((item.get("id") or "").strip()):
                    loop.run_in_executor(EXECUTOR, fetch_avatar_background, item)

            # R2: 等待间隔，新扫描启动时立即退出
            try:
                await asyncio.wait_for(event.wait(), timeout=_MONITOR_INTERVAL_SEC)
                _log("info", "monitor cancelled by new scan (token=%d)", token)
                return
            except asyncio.TimeoutError:
                pass  # 正常超时 -> 继续下一轮
    finally:
        if token == _MONITOR_TOKEN:
            SCAN_STATE_STORE.set_monitoring(False)
            await broadcast_scan_status()


def _load_channels_csv(app_dir: str) -> list[dict]:
    rows = read_all_csv_rows_in_dir(app_dir)
    seen: set[tuple[str, str, str]] = set()
    deduped: list[dict] = []
    for r in rows:
        cid = (r.get("id") or "").strip()
        raw_url = (r.get("url") or r.get("URL") or "").strip()
        title = (r.get("title") or r.get("name") or "").strip()
        if not cid and not raw_url:
            continue
        key = (cid.lower(), raw_url.lower(), title)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)
    return deduped
