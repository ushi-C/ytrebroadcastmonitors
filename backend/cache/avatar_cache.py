"""
avatar_cache.py
───────────────
频道头像缓存门面：
  1. 内存缓存：channel_id -> remote URL（持久化 JSON）
  2. 磁盘缓存：avatar_cache/ 目录中的 .img 文件

公共接口：
- init()
- load_channel_avatar_cache() / save_channel_avatar_cache()
- get_avatar_disk_path(url)
- get_cached_avatar(channel_id)
- fetch_channel_avatar(url, cid)
- start_cleanup_loop()
- start_flush_loop() / flush()  — 定时刷盘 + 退出强制保存
- set_broadcast_fn(fn)          — 注册 WS 广播回调
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
import urllib.parse

from .avatar_cache_components import AvatarDiskCache, ChannelAvatarMemoryCache
from .avatar_innertube import fetch_avatar_via_innertube

AVATAR_CACHE_MAX_BYTES      = 80 * 1024 * 1024
AVATAR_CACHE_MAX_AGE_SEC    = 30 * 24 * 3600
AVATAR_CACHE_CLEAN_INTERVAL = 3600
CHANNEL_AVATAR_CACHE_MAX_ITEMS = 5_000

# 定时刷盘间隔（秒）
_FLUSH_INTERVAL_SEC = 12

_YDL_TIMEOUT = 8

_logger: logging.Logger | None = None
_cache_file: str = ""
_cache_dir: str = ""

_inflight_fetch_lock = threading.Lock()
_inflight_fetch: set[str] = set()

# 组件实例，由 init() 正式初始化
_memory_cache: ChannelAvatarMemoryCache | None = None
_disk_cache: AvatarDiskCache | None = None

# ── 刷盘机制：内存实时 + 异步定时持久化 ──
_dirty_lock = threading.Lock()
_is_dirty = False
_flush_stop_event = threading.Event()

# ── WS 广播回调（由 api.py 注入，用于头像更新后推送前端）──
_broadcast_fn = None


def init(
    logger: logging.Logger,
    cache_file: str,
    cache_dir: str,
) -> None:
    """应用启动时注入依赖，必须在使用其他接口前调用。"""
    global _logger, _cache_file, _cache_dir, _memory_cache, _disk_cache
    _logger     = logger
    _cache_file = cache_file
    _cache_dir  = cache_dir

    os.makedirs(_cache_dir, exist_ok=True)

    _memory_cache = ChannelAvatarMemoryCache(
        max_items=CHANNEL_AVATAR_CACHE_MAX_ITEMS,
        log=_log,
    )
    _disk_cache = AvatarDiskCache(
        cache_dir=_cache_dir,
        max_bytes=AVATAR_CACHE_MAX_BYTES,
        max_age_sec=AVATAR_CACHE_MAX_AGE_SEC,
    )


# ── 内存缓存 ─────────────────────────────────────────────────────────────────

def load_channel_avatar_cache() -> None:
    _memory_cache.load_from_file(_cache_file)


def save_channel_avatar_cache() -> None:
    _memory_cache.save_to_file(_cache_file)


def _set_channel_cache(channel_id: str, avatar_url: str) -> None:
    _memory_cache.set(channel_id, avatar_url)
    _mark_dirty()


def _mark_dirty() -> None:
    """标记内存缓存已变更，等待定时刷盘。"""
    global _is_dirty
    with _dirty_lock:
        _is_dirty = True


def _persist_avatar(channel_id: str, avatar_url: str) -> str:
    """
    更新内存缓存并标记 dirty，不再即时写盘。
    内存绝对实时：调用返回后 get_cached_avatar() 立即可见。
    磁盘延迟写入：由后台 _flush_loop 每 12s 集中刷盘。
    """
    _set_channel_cache(channel_id, avatar_url)
    _log("info", "[avatar-cache] cached channel_id=%s (dirty, deferred flush)", channel_id)

    # 触发 WS 广播：头像更新后推送前端
    if _broadcast_fn:
        try:
            _broadcast_fn()
        except Exception as exc:
            _log("warning", "[avatar-cache] broadcast callback failed: %s", exc)

    return avatar_proxy_url(avatar_url)


# ── 定时刷盘机制 ──────────────────────────────────────────────────────────────

def start_flush_loop() -> None:
    """启动后台定时刷盘线程（每 12 秒检查一次 is_dirty）。"""
    t = threading.Thread(target=_flush_loop, daemon=True)
    t.start()
    _log("info", "[avatar-cache] flush loop started (interval=%ds)", _FLUSH_INTERVAL_SEC)


def _flush_loop() -> None:
    while not _flush_stop_event.wait(_FLUSH_INTERVAL_SEC):
        try:
            _flush_if_dirty()
        except Exception:
            _log("exception", "[avatar-cache] flush loop error")


def _flush_if_dirty() -> None:
    global _is_dirty
    with _dirty_lock:
        if not _is_dirty:
            return
        _is_dirty = False
    # 在锁外执行 I/O，避免阻塞读写
    _memory_cache.save_to_file(_cache_file)


def flush() -> None:
    """强制刷盘（供 FastAPI lifespan 退出时调用）。"""
    _flush_stop_event.set()
    _flush_if_dirty()
    _log("info", "[avatar-cache] flush completed on shutdown")


def set_broadcast_fn(fn) -> None:
    """注册 WS 广播回调函数（由 api.py 注入）。"""
    global _broadcast_fn
    _broadcast_fn = fn


# ── 磁盘图片缓存 ──────────────────────────────────────────────────────────────

def get_avatar_disk_path(remote_url: str) -> str:
    """确保 remote_url 对应图片存在于磁盘缓存并返回路径。"""
    return _disk_cache.get_or_download(remote_url)


def avatar_proxy_url(remote_url: str) -> str:
    if not remote_url:
        return ""
    return "/api/avatar?u=" + urllib.parse.quote(remote_url, safe="")


def get_cached_avatar(channel_id: str) -> str:
    """仅从内存缓存读取频道头像，不触发任何网络请求。"""
    if not channel_id:
        return ""
    cached = _memory_cache.get(channel_id)
    if not cached:
        return ""
    return avatar_proxy_url(cached)


def is_avatar_fetch_inflight(channel_id: str) -> bool:
    """该频道是否已有进行中的头像抓取（含 yt-dlp 重试与 innertube 兜底）。"""
    cid = (channel_id or "").strip()
    if not cid:
        return False
    with _inflight_fetch_lock:
        return cid in _inflight_fetch


def fetch_channel_avatar(channel_url: str, channel_id: str) -> str:
    """获取频道头像并返回代理 URL，失败时返回空字符串。"""
    from yt_dlp import YoutubeDL

    cached = _memory_cache.get(channel_id) if channel_id else None
    if cached:
        _log("info", "[avatar-cache] hit channel_id=%s", channel_id)
        return avatar_proxy_url(cached)

    inflight_key = channel_id or channel_url
    with _inflight_fetch_lock:
        if inflight_key in _inflight_fetch:
            return ""
        _inflight_fetch.add(inflight_key)

    base_url = re.sub(r'/live$', '', channel_url.rstrip('/'))
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "playlist_items": "0",
        "socket_timeout": _YDL_TIMEOUT,
    }

    try:
        for attempt in range(2):
            try:
                with YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(base_url, download=False)
                    thumbnails = (info or {}).get("thumbnails", [])
                    if not thumbnails:
                        raise Exception("no thumbnails")

                    avatar_url = ""
                    for t in thumbnails:
                        url = t.get("url", "")
                        m = re.search(r"=s(\d+)", url)
                        if not m:
                            continue
                        size = int(m.group(1))
                        if size < 176 or size > 900:
                            continue
                        avatar_url = url
                        break

                    if not avatar_url:
                        raise Exception("empty avatar url")

                    return _persist_avatar(channel_id, avatar_url)

            except Exception as e:
                _log(
                    "warning",
                    "[avatar-cache] fetch failed attempt=%s channel_id=%s err=%s",
                    attempt + 1,
                    channel_id,
                    str(e),
                )
                if attempt == 0:
                    time.sleep(1)

        if channel_id:
            fallback_url = fetch_avatar_via_innertube(channel_id)
            if fallback_url:
                return _persist_avatar(channel_id, fallback_url)
    finally:
        with _inflight_fetch_lock:
            _inflight_fetch.discard(inflight_key)

    return ""


# ── 后台清理 ──────────────────────────────────────────────────────────────────

def start_cleanup_loop() -> None:
    t = threading.Thread(target=_cleanup_loop, daemon=True)
    t.start()


def _cleanup_loop() -> None:
    while True:
        time.sleep(AVATAR_CACHE_CLEAN_INTERVAL)
        try:
            _cleanup_avatar_cache()
        except Exception as exc:
            _log("warning", "[avatar-cache] cleanup loop error: %s", exc)


def _cleanup_avatar_cache():
    _disk_cache.cleanup()


# ── 内部工具 ──────────────────────────────────────────────────────────────────

def _log(level: str, msg: str, *args, **kwargs) -> None:
    if _logger:
        getattr(_logger, level)(msg, *args, **kwargs)
