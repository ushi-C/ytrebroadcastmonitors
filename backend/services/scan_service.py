"""
scan_service.py
───────────────
API 编排服务层，将路由层的编排代码集中管理。
"""

from __future__ import annotations

import asyncio
import os

from ..services import scanner as _sc
from ..utils.channel_csv_reader import read_all_csv_rows_in_dir


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
    """读取目录下全部 CSV 并返回前端搜索所需格式（含轻量去重）。"""
    app_dir = app_dir_fn()
    if not os.path.isdir(app_dir):
        return []

    seen: set[tuple[str, str, str]] = set()
    merged: list[dict[str, str]] = []
    for r in read_all_csv_rows_in_dir(app_dir):
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
