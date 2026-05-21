"""
scan_service.py
───────────────
API 编排服务层，将路由层的编排代码集中管理。
"""

from __future__ import annotations

import asyncio

from ..cache import avatar_cache as _ac
from ..services import scanner as _sc
from ..utils.channel_csv_reader import read_all_csv_rows_in_dir, resolve_channels_dir


async def check_single_channel(query: str, title: str = "") -> dict | None:
    """执行单频道检测，返回扫描结果或 None。"""
    target_url, cid = _sc.normalize_channel_live_url(query)
    handle_mark = _sc.extract_handle_mark(target_url) or _sc.extract_handle_mark(query)
    name_raw = title or None

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        _sc.EXECUTOR, _sc.check_live_sync, target_url, cid, name_raw, handle_mark
    )


def load_channels_for_search(app_dir_fn) -> list[dict[str, str]]:
    """读取 channels 目录下全部 CSV 并返回前端搜索所需格式（含轻量去重）。"""
    channels_dir = resolve_channels_dir(app_dir_fn())
    if not channels_dir:
        return []

    seen: set[tuple[str, str, str]] = set()
    merged: list[dict[str, str]] = []
    for r in read_all_csv_rows_in_dir(channels_dir):
        item = {
            "id":    (r.get("id") or "").strip(),
            "url":   (r.get("url") or r.get("URL") or "").strip(),
            "title": (r.get("title") or r.get("name") or "").strip(),
        }
        if not item["id"] and not item["url"]:
            continue
        dedup_key = (item["id"].lower(), item["url"].lower(), item["title"])
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        merged.append(item)
    return merged


async def trigger_refresh_scan() -> str:
    """触发全量扫描，返回 started / busy。"""
    if not _sc.SCAN_STATE_STORE.is_running:
        _sc.SCAN_STATE_STORE.reset_for_new_scan()
        asyncio.create_task(_sc.start_scan_task())
        return "started"
    return "busy"


def get_scan_status() -> dict:
    """返回当前扫描状态的快照副本。"""
    state = _sc.SCAN_STATE_STORE.get_snapshot()

    return {
        "is_running": state["is_running"],
        "is_monitoring": state.get("is_monitoring", False),
        "progress":   state["progress"],
        "total":      state["total"],
        "results":    state["results"],  
    }


async def schedule_missing_avatar_fetches(results: list[dict]) -> None:
    """
    为尚未命中内存缓存的直播条目排队后台抓取（含 innertube 兜底）。
    不阻塞 status 响应；写入缓存后由下次 get_status 派生 avatar 注入前端 card。
    """
    if not results:
        return
    loop = asyncio.get_running_loop()
    for item in results:
        cid = (item.get("id") or "").strip()
        if not cid:
            continue
        if _ac.get_cached_avatar(cid) or _ac.is_avatar_fetch_inflight(cid):
            continue
        channel_live_url = (item.get("channel_live_url") or "").strip()
        if not channel_live_url:
            continue
        loop.run_in_executor(_sc.EXECUTOR, _sc.fetch_avatar_background, item)
