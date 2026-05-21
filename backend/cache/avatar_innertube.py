"""
avatar_innertube.py
───────────────────
yt-dlp 拉取头像失败时的 innertube browse 兜底。
"""

from __future__ import annotations

import re
import threading
import time

import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "en-US,en;q=0.9",
}

_CONFIG_TTL_SEC = 3600

_config_lock = threading.Lock()
_config_cached_at = 0.0
_config_key: str | None = None
_config_version: str | None = None


def _safe_get(data, path: list[str]):
    for k in path:
        if isinstance(data, dict) and k in data:
            data = data[k]
        else:
            return None
    return data


def _extract_avatar(res: dict) -> str | None:
    paths = [
        ["header", "c4TabbedHeaderRenderer", "avatar"],
        ["header", "pageHeaderRenderer", "content", "pageHeaderViewModel", "image"],
        ["metadata", "channelMetadataRenderer", "avatar"],
    ]

    for path in paths:
        data = _safe_get(res, path)
        if not data:
            continue

        thumbnails = data.get("thumbnails")
        if isinstance(thumbnails, list) and thumbnails:
            url = thumbnails[-1].get("url")
            if url:
                return url

    return None


def _get_innertube_config() -> tuple[str | None, str | None]:
    global _config_cached_at, _config_key, _config_version

    now = time.time()
    with _config_lock:
        if (
            _config_key
            and _config_version
            and now - _config_cached_at < _CONFIG_TTL_SEC
        ):
            return _config_key, _config_version

    try:
        resp = requests.get("https://www.youtube.com", headers=HEADERS, timeout=10)
        resp.raise_for_status()
        html = resp.text
    except requests.RequestException:
        return None, None

    key_match = re.search(r'"INNERTUBE_API_KEY":"(.*?)"', html)
    ver_match = re.search(r'"INNERTUBE_CLIENT_VERSION":"(.*?)"', html)
    if not key_match or not ver_match:
        return None, None

    key, version = key_match.group(1), ver_match.group(1)
    with _config_lock:
        _config_key = key
        _config_version = version
        _config_cached_at = now
    return key, version


def fetch_avatar_via_innertube(channel_id: str) -> str | None:
    """通过 innertube browse 获取频道头像远程 URL，失败返回 None。"""
    channel_id = (channel_id or "").strip()
    if not channel_id:
        return None

    key, version = _get_innertube_config()
    if not key or not version:
        return None

    url = f"https://www.youtube.com/youtubei/v1/browse?key={key}"
    payload = {
        "context": {
            "client": {
                "clientName": "WEB",
                "clientVersion": version,
            }
        },
        "browseId": channel_id,
    }

    try:
        resp = requests.post(url, json=payload, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        res = resp.json()
    except (requests.RequestException, ValueError):
        return None

    return _extract_avatar(res)
