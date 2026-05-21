"""
avatar_cache_components.py
──────────────────────────
头像缓存子组件：
- ChannelAvatarMemoryCache：channel_id -> avatar_url 的内存 LRU 缓存与持久化
- AvatarDiskCache：磁盘头像缓存的下载与清理
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import urllib.request
from typing import Callable


class ChannelAvatarMemoryCache:
    """管理 channel_id -> remote avatar URL 的 LRU 缓存。"""

    def __init__(self, max_items: int, log: Callable[..., None]) -> None:
        self._max_items = max_items
        self._log = log
        self._lock = threading.Lock()
        self._data: dict[str, str] = {}

    def load_from_file(self, cache_file: str) -> None:
        if not os.path.exists(cache_file):
            return
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                normalized = {str(k): str(v) for k, v in data.items() if k and v}
                if len(normalized) > self._max_items:
                    trim = len(normalized) - self._max_items
                    normalized = dict(list(normalized.items())[trim:])
                self._data = normalized
                self._log("info", "[avatar-cache] loaded %s channel entries", len(self._data))
        except Exception as exc:
            self._log("exception", "[avatar-cache] load failed", exc_info=exc)

    def save_to_file(self, cache_file: str) -> None:
        with self._lock:
            data = dict(self._data)
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
            self._log("info", "[avatar-cache] saved %s channel entries", len(data))
        except Exception as exc:
            self._log("exception", "[avatar-cache] save failed", exc_info=exc)

    def get(self, channel_id: str) -> str | None:
        if not channel_id:
            return None
        with self._lock:
            cached = self._data.get(channel_id)
            if cached:
                # LRU 刷新：移除后重新插入到末尾（依赖 Python 3.7+ dict 插入序）
                self._data.pop(channel_id, None)
                self._data[channel_id] = cached
            return cached

    def set(self, channel_id: str, avatar_url: str) -> None:
        if not channel_id or not avatar_url:
            return
        with self._lock:
            self._data[channel_id] = avatar_url
            if len(self._data) > self._max_items:
                overflow = len(self._data) - self._max_items
                for old_key in list(self._data.keys())[:overflow]:
                    self._data.pop(old_key, None)


class AvatarDiskCache:
    """管理头像磁盘缓存的下载和清理。"""

    def __init__(self, cache_dir: str, max_bytes: int, max_age_sec: int) -> None:
        self.cache_dir = cache_dir
        self.max_bytes = max_bytes
        self.max_age_sec = max_age_sec

    def get_path(self, remote_url: str) -> str:
        h = hashlib.sha1(remote_url.encode("utf-8")).hexdigest()
        return os.path.join(self.cache_dir, f"{h}.img")

    def get_or_download(self, remote_url: str) -> str:
        path = self.get_path(remote_url)
        if not os.path.exists(path):
            req = urllib.request.Request(
                remote_url,
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
                    "Referer": "https://www.youtube.com/",
                },
            )
            with urllib.request.urlopen(req, timeout=6) as resp:
                max_bytes = 2 * 1024 * 1024
                data = resp.read(max_bytes + 1)
            if len(data) > max_bytes:
                raise ValueError("image too large")
            with open(path, "wb") as f:
                f.write(data)
        return path

    def cleanup(self) -> None:
        if not os.path.isdir(self.cache_dir):
            return

        now = time.time()
        entries = self._collect_entries()

        for mtime, _size, path in entries:
            if now - mtime > self.max_age_sec:
                try:
                    os.remove(path)
                except OSError:
                    pass

        entries = self._collect_entries()
        total = sum(s for _m, s, _p in entries)
        if total <= self.max_bytes:
            return

        entries.sort(key=lambda x: x[0])
        for _mtime, size, path in entries:
            if total <= self.max_bytes:
                break
            try:
                os.remove(path)
                total -= size
            except OSError:
                pass

    def _collect_entries(self) -> list[tuple[float, int, str]]:
        result: list[tuple[float, int, str]] = []
        try:
            for name in os.listdir(self.cache_dir):
                if not name.endswith(".img"):
                    continue
                p = os.path.join(self.cache_dir, name)
                try:
                    st = os.stat(p)
                    result.append((st.st_mtime, st.st_size, p))
                except OSError:
                    pass
        except OSError:
            pass
        return result
