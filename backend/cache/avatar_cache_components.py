"""
avatar_cache_components.py
──────────────────────────
头像缓存子组件：
- ChannelAvatarMemoryCache：channel_id -> avatar_url 的内存 LRU 缓存与持久化
- AvatarDiskCache：磁盘头像缓存的下载与清理
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import shutil
import socket
import threading
import time
import urllib.parse
from typing import Callable

import requests


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
        except (json.JSONDecodeError, ValueError) as exc:
            # R4: 缓存文件损坏 — 备份 + 尝试恢复
            self._log("warning", "[avatar-cache] cache file corrupted, attempting recovery: %s", exc)
            self._recover_from_corrupt(cache_file)
        except Exception as exc:
            self._log("exception", "[avatar-cache] load failed", exc_info=exc)

    def _recover_from_corrupt(self, cache_file: str) -> None:
        """R4: 缓存文件损坏时的恢复策略：备份损坏文件 + 尝试逐条提取有效条目。"""
        corrupt_backup = cache_file + ".corrupt"
        try:
            shutil.copy2(cache_file, corrupt_backup)
            self._log("info", "[avatar-cache] corrupt file backed up to %s", corrupt_backup)
        except Exception as backup_exc:
            self._log("warning", "[avatar-cache] failed to backup corrupt file: %s", backup_exc)

        recovered = self._try_recover_partial(cache_file)
        if recovered:
            self._data = recovered
            self._log("info", "[avatar-cache] recovered %d entries from corrupt file", len(recovered))
        else:
            self._data = {}
            self._log("warning", "[avatar-cache] no entries could be recovered, starting fresh")

    def _try_recover_partial(self, cache_file: str) -> dict[str, str]:
        """从损坏的 JSON 文件中用正则提取有效的 channel_id -> url 对。"""
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                raw = f.read()
        except Exception:
            return {}

        pattern = re.compile(r'"([^"]+)"\s*:\s*"(https?://[^"]+)"')
        result: dict[str, str] = {}
        for key, url in pattern.findall(raw):
            if key and url:
                result[str(key)] = str(url)
            if len(result) >= self._max_items:
                break
        return result

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


# ── SSRF 防护：域名白名单 + IP 私有地址校验 ─────────────────────────────────

_ALLOWED_AVATAR_DOMAINS = frozenset({
    "ytimg.com",
    "googleusercontent.com",
    "ggpht.com",
    "youtube.com",
})

_PRIVATE_IP_RANGES: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = [
    ipaddress.ip_network("0.0.0.0/8"),        # 当前网络（仅 IPv4）
    ipaddress.ip_network("10.0.0.0/8"),        # A 类私有
    ipaddress.ip_network("127.0.0.0/8"),       # 回环
    ipaddress.ip_network("169.254.0.0/16"),    # 链路本地
    ipaddress.ip_network("172.16.0.0/12"),     # B 类私有
    ipaddress.ip_network("192.168.0.0/16"),    # C 类私有
    ipaddress.ip_network("224.0.0.0/4"),       # 多播
    ipaddress.ip_network("240.0.0.0/4"),       # 保留（E 类）
    ipaddress.ip_network("::1/128"),           # IPv6 回环
    ipaddress.ip_network("fc00::/7"),          # IPv6 唯一本地
    ipaddress.ip_network("fe80::/10"),         # IPv6 链路本地
]

_AVATAR_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    "Referer": "https://www.youtube.com/",
}


def _validate_avatar_domain(url: str) -> str:
    """校验 URL 域名是否在白名单中。

    严格匹配域名（含子域名），防御 ytimg.com.attacker.com 类绕过。
    返回规范化后的主机名。
    """
    parsed = urllib.parse.urlparse(url)
    hostname = (parsed.hostname or "").lower()
    if not hostname:
        raise ValueError("invalid URL: no hostname")

    for allowed in _ALLOWED_AVATAR_DOMAINS:
        if hostname == allowed or hostname.endswith("." + allowed):
            return hostname

    raise ValueError(f"domain not allowed: {hostname}")


def _is_private_ip(ip_str: str) -> bool:
    """判断 IP 是否属于私有/保留地址段。"""
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True  # 无法解析则拦截
    return any(ip in net for net in _PRIVATE_IP_RANGES)


def _validate_remote_ip(hostname: str) -> None:
    """预防 DNS 重绑定/恶意重定向——校验最终主机名解析的所有 IP。

    若任一解析结果为私有/保留地址，直接拦截。
    """
    try:
        addrs = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError(f"DNS resolution failed for {hostname}") from exc

    for family, _, _, _, sockaddr in addrs:
        ip = str(sockaddr[0])
        if _is_private_ip(ip):
            raise ValueError(f"blocked: {hostname} resolves to private IP {ip}")


# ── AvatarDiskCache ──────────────────────────────────────────────────────────

class AvatarDiskCache:
    """管理头像磁盘缓存的下载和清理。"""

    def __init__(self, cache_dir: str, max_bytes: int, max_age_sec: int) -> None:
        self.cache_dir = cache_dir
        self.max_bytes = max_bytes
        self.max_age_sec = max_age_sec
        # 连接复用 session（requests 内置连接池）
        self._session = requests.Session()
        self._session.max_redirects = 3
        self._session.headers.update(_AVATAR_HEADERS)

    def get_path(self, remote_url: str) -> str:
        h = hashlib.sha1(remote_url.encode("utf-8")).hexdigest()
        return os.path.join(self.cache_dir, f"{h}.img")

    def get_or_download(self, remote_url: str) -> str:
        path = self.get_path(remote_url)
        if os.path.exists(path):
            return path

        # ── 第一层：域名白名单校验 ──
        hostname = _validate_avatar_domain(remote_url)

        # ── 第二层：DNS IP 预检（防 DNS 重绑定）──
        _validate_remote_ip(hostname)

        # ── 发起请求（requests 自动处理重定向，max_redirects=3）──
        try:
            resp = self._session.get(remote_url, timeout=6, stream=True)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise ValueError(f"download failed: {exc}") from exc

        # ── 第三层：重定向后最终主机名 IP 再校验 ──
        final_hostname = urllib.parse.urlparse(resp.url).hostname or ""
        if final_hostname.lower() != hostname:
            _validate_remote_ip(final_hostname)

        # ── 流式读取，限制大小 ──
        max_bytes = 2 * 1024 * 1024
        chunks: list[bytes] = []
        total = 0
        for chunk in resp.iter_content(chunk_size=8192):
            total += len(chunk)
            if total > max_bytes:
                resp.close()
                raise ValueError("image too large")
            chunks.append(chunk)

        data = b"".join(chunks)
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
