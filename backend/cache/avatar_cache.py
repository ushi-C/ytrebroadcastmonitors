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
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
import urllib.parse

from .avatar_cache_components import AvatarDiskCache, ChannelAvatarMemoryCache

AVATAR_CACHE_MAX_BYTES      = 80 * 1024 * 1024
AVATAR_CACHE_MAX_AGE_SEC    = 30 * 24 * 3600
AVATAR_CACHE_CLEAN_INTERVAL = 3600
CHANNEL_AVATAR_CACHE_MAX_ITEMS = 5_000

_YDL_TIMEOUT = 8

_logger: logging.Logger | None = None
_cache_file: str = ""
_cache_dir: str = ""
_scan_state: dict | None = None

_inflight_fetch_lock = threading.Lock()
_inflight_fetch: set[str] = set()

# 组件实例，由 init() 正式初始化
_memory_cache: ChannelAvatarMemoryCache | None = None
_disk_cache: AvatarDiskCache | None = None


def init(
    logger: logging.Logger,
    cache_file: str,
    cache_dir: str,
    scan_state: dict,
) -> None:
    """应用启动时注入依赖，必须在使用其他接口前调用。"""
    global _logger, _cache_file, _cache_dir, _scan_state, _memory_cache, _disk_cache
    _logger     = logger
    _cache_file = cache_file
    _cache_dir  = cache_dir
    _scan_state = scan_state

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

                    _set_channel_cache(channel_id, avatar_url)
                    save_channel_avatar_cache()
                    _log("info", "[avatar-cache] saved channel_id=%s", channel_id)
                    return avatar_proxy_url(avatar_url)

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
        except Exception:
            pass


def _cleanup_avatar_cache() -> None:
    if _scan_state and _scan_state.get("is_running"):
        return
    _disk_cache.cleanup()


# ── 内部工具 ──────────────────────────────────────────────────────────────────

def _log(level: str, msg: str, *args, **kwargs) -> None:
    if _logger:
        getattr(_logger, level)(msg, *args, **kwargs)
