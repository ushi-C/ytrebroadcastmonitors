"""
scanner.py
──────────
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
import os
import re
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from yt_dlp import YoutubeDL

from ..cache import avatar_cache as _ac
from ..utils.channel_csv_reader import read_all_csv_rows_in_dir, resolve_channels_dir
from ..models.scan_state_store import ScanStateStore
from ..services import youtube_probe as _yt_probe

EXECUTOR         = ThreadPoolExecutor(max_workers=60)
SCAN_STATE_STORE = ScanStateStore()
# SCAN_STATE dict alias removed: state is now a deep-copy snapshot, use SCAN_STATE_STORE methods directly
_MONITOR_INTERVAL_SEC = 300
_MONITOR_TOKEN = 0

_HEAD_TIMEOUT = 4
_YDL_TIMEOUT  = 8

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1F\x7F]")
_HEAD_HEADERS     = {"User-Agent": "Mozilla/5.0"}

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
    落在 /watch?v= 或仍含 /live → 可能在播，返回 True。
    """
    try:
        req = urllib.request.Request(url, method="GET", headers=_HEAD_HEADERS)
        with urllib.request.urlopen(req, timeout=_HEAD_TIMEOUT) as resp:
            final_url = resp.geturl()
            return "watch?v=" in final_url or "/live" in final_url
    except Exception:
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
    except Exception:
        pass
    return None


def fetch_avatar_background(item: dict) -> None:
    """后台预热头像缓存。avatar 是派生字段，由 API 层在响应时注入，此处只写缓存。"""
    try:
        channel_id = (item.get("id") or "").strip()
        if not channel_id:
            return
        # 已命中内存缓存，无需重复 fetch
        if _ac.get_cached_avatar(channel_id):
            return
        channel_live_url = (item.get("channel_live_url") or "").strip()
        if not channel_live_url:
            return
        # ✔ 只做缓存预热，不写回 scan state（由 API 层派生）
        _ac.fetch_channel_avatar(channel_live_url, channel_id)
    except Exception:
        pass


# ── 监测 ─────────────────────────────────────

def classify_ytdlp_exception(e: Exception) -> str:
    """
    根据 yt-dlp 抛出的异常消息判断频道状态。

    返回值：
      offline    — 频道当前未开播
      upcoming   — 预定直播尚未开始
      ended      — 直播已结束（转为录播）
      terminated — 账号已被封禁
      js_error   — 本地缺少 JS 运行时（环境问题）
      unknown    — 无法识别的异常
    """
    msg = str(e)

    if "not currently live" in msg:
        return "offline"

    if "will begin in" in msg:
        return "upcoming"

    if "has ended" in msg:
        return "ended"

    if "This account has been terminated" in msg:
        return "terminated"

    if "No supported JavaScript runtime" in msg:
        return "js_error"

    return "unknown"


def _recheck_live_ytdlp(item: dict) -> dict | None:
    """
    用 yt-dlp 直接检测 channel_live_url 主页是否仍在直播。

    返回规则：
      is_live=True                          → 保留卡片
      is_live=False 或 info 为空            → 移除卡片
      offline / ended / upcoming / terminated → 明确下播，移除卡片
      js_error / unknown 异常               → 保守保留
    """
    url = (item.get("channel_live_url") or item.get("url") or "").strip()
    if not url:
        return item  # 无链接，保守保留

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
            return item  # ✅ 仍在播

        return None  # ❌ 明确不在播（录播或无直播）

    except Exception as e:
        state = classify_ytdlp_exception(e)
        _log("debug", "recheck [%s] state=%s | %s", url, state, e)

        # 明确下播：移除卡片
        if state in ("offline", "ended", "upcoming", "terminated"):
            return None

        # 环境问题：保守保留
        if state == "js_error":
            return item

        # 未知异常：保守保留
        return item


def _monitor_recheck_sync(item: dict) -> dict | None:
    """监控复检入口，供线程池调用。"""
    return _recheck_live_ytdlp(item)


# ── 频道标识规范化 ────────────────────────────────────────────────────────────

def normalize_channel_live_url(q: str) -> tuple[str, str]:
    """把各种形式的频道标识统一转成 /live URL，返回 (target_url, channel_id)。"""
    q = q.strip()
    if re.match(r'^UC[A-Za-z0-9_-]{20,}$', q):
        return f"https://www.youtube.com/channel/{q}/live", q
    if q.startswith("http"):
        base = q.rstrip("/")
        if base.endswith("/live"):
            m = re.search(r'/channel/(UC[A-Za-z0-9_-]+)', base)
            return base, (m.group(1) if m else "")
        m = re.search(r'/channel/(UC[A-Za-z0-9_-]+)', base)
        if m:
            cid = m.group(1)
            return f"https://www.youtube.com/channel/{cid}/live", cid
        if re.search(r'/@([^/?#]+)', base):
            return f"{base}/live", ""
        return f"{base}/live", ""
    if q.startswith("@"):
        return f"https://www.youtube.com/{q}/live", ""
    return f"https://www.youtube.com/@{q}/live", ""


# ── CSV 批量扫描协程 ──────────────────────────────────────────────────────────

async def start_scan_task() -> None:
    """从应用目录下全部 CSV 批量扫描直播，更新 SCAN_STATE。"""
    if not _yt_probe.can_run_youtube_workflows():
        _log("warning", "Scan blocked: YouTube network unavailable")
        SCAN_STATE_STORE.reset_for_new_scan()
        SCAN_STATE_STORE.set_running(False)
        SCAN_STATE_STORE.set_monitoring(False)
        return
    app_dir = _app_dir_fn()
    channels_dir = resolve_channels_dir(app_dir)
    if not channels_dir:
        _log("warning", "Channels directory not found (app_dir=%s)", app_dir)
        SCAN_STATE_STORE.set_running(False)
        return

    channels = _load_channels_csv(channels_dir)
    if not channels:
        SCAN_STATE_STORE.set_running(False)
        return

    global _MONITOR_TOKEN
    _MONITOR_TOKEN += 1
    SCAN_STATE_STORE.reset_for_new_scan()
    SCAN_STATE_STORE.set_total(len(channels))
    loop       = asyncio.get_running_loop()
    batch_size = 15

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
    finally:
        SCAN_STATE_STORE.set_running(False)
        asyncio.create_task(start_live_monitor_task(_MONITOR_TOKEN))


async def start_live_monitor_task(token: int) -> None:
    """
    扫描结束后每 5 分钟复检一轮在线卡片。
    并发数限制为 3，直接调用 yt-dlp 检测 /live 主页。
    直到卡片清空或下一轮全量扫描开始时退出。
    """
    if token != _MONITOR_TOKEN:
        return

    SCAN_STATE_STORE.set_monitoring(True)
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
        await asyncio.sleep(_MONITOR_INTERVAL_SEC)
        while token == _MONITOR_TOKEN and not SCAN_STATE_STORE.is_running:
            current_items = list(SCAN_STATE_STORE.get_snapshot()["results"])
            if not current_items:
                break

            tasks     = [_recheck_with_limit(item) for item in current_items]
            refreshed = await asyncio.gather(*tasks)

            live_results = [r for r in refreshed if r]
            SCAN_STATE_STORE.replace_results(live_results)

            if not live_results:
                break

            for item in live_results:
                if not _ac.get_cached_avatar((item.get("id") or "").strip()):
                    loop.run_in_executor(EXECUTOR, fetch_avatar_background, item)

            await asyncio.sleep(_MONITOR_INTERVAL_SEC)
    finally:
        if token == _MONITOR_TOKEN:
            SCAN_STATE_STORE.set_monitoring(False)


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
