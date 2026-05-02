"""
scanner.py
──────────
YouTube 直播检测逻辑

公共接口
--------
SCAN_STATE                      全局扫描状态字典（由 api.py 读取）
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
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from yt_dlp import YoutubeDL

from ..cache import avatar_cache as _ac
from ..utils.channel_csv_reader import read_channels_csv_rows
from ..models.scan_state_store import ScanStateStore

EXECUTOR         = ThreadPoolExecutor(max_workers=60)
SCAN_STATE_STORE = ScanStateStore()
SCAN_STATE: dict = SCAN_STATE_STORE.state

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
                avatar_cached   = _ac.get_cached_avatar(real_channel_id)
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
                    "avatar": avatar_cached or "",
                    "channel_live_url": url,
                }
    except Exception:
        pass
    return None


def fetch_avatar_background(item: dict) -> None:
    try:
        channel_id = (item.get("id") or "").strip()
        if not channel_id:
            return

        avatar_cached = _ac.get_cached_avatar(channel_id)
        if avatar_cached:
            avatar = avatar_cached
        else:
            channel_live_url = (item.get("channel_live_url") or "").strip()
            if not channel_live_url:
                return
            avatar = _ac.fetch_channel_avatar(channel_live_url, channel_id)

        if avatar:
            for r in SCAN_STATE["results"]:
                if r.get("id") == channel_id:
                    r["avatar"] = avatar
                    break

    except Exception:
        pass


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
    """从 channels.csv 批量扫描直播，更新 SCAN_STATE。"""
    file_path = os.path.join(_app_dir_fn(), "channels.csv")
    if not os.path.exists(file_path):
        SCAN_STATE_STORE.set_running(False)
        return

    channels = _load_channels_csv(file_path)
    if not channels:
        SCAN_STATE_STORE.set_running(False)
        return

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
                results     = await asyncio.gather(*tasks)
                live_results = [r for r in results if r]
                SCAN_STATE_STORE.add_results(live_results)
                for item in live_results:
                    loop.run_in_executor(EXECUTOR, fetch_avatar_background, item)

            SCAN_STATE_STORE.add_progress(len(batch))
    finally:
        SCAN_STATE_STORE.set_running(False)


def _load_channels_csv(file_path: str) -> list[dict]:
    return read_channels_csv_rows(file_path)
