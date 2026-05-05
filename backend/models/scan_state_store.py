"""
scan_state_store.py
───────────────────
扫描状态存储（线程安全）。
"""

from __future__ import annotations

import copy
from threading import RLock
from typing import Any


class ScanStateStore:
    """对扫描状态字典进行受控读写。"""

    def __init__(self) -> None:
        self._lock = RLock()
        self._state: dict[str, Any] = {
            "is_running": False,
            "is_monitoring": False,
            "progress": 0,
            "total": 0,
            "results": [],
        }

    @property
    def state(self) -> dict[str, Any]:
        """返回内部状态的深拷贝（snapshot-only access; safe for external read, not for mutation）。"""
        with self._lock:
            return copy.deepcopy(self._state)

    def get_snapshot(self) -> dict[str, Any]:
        """与 state 属性等价，语义更明确，供 API 层使用。"""
        with self._lock:
            return copy.deepcopy(self._state)

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._state["is_running"]

    def reset_for_new_scan(self) -> None:
        with self._lock:
            self._state.update(
                is_running=True,
                is_monitoring=False,
                progress=0,
                total=0,
                results=[],
            )

    def set_total(self, total: int) -> None:
        with self._lock:
            self._state["total"] = total

    def add_progress(self, count: int) -> None:
        with self._lock:
            self._state["progress"] += count

    # ── results write boundary ───────────────────────────────────────────────

    @staticmethod
    def _strip_avatar(item: dict) -> dict:
        """
        avatar 是响应时派生的字段，永不存入 state。
        在每个写入口统一剔除，保证 state 模型收敛。
        """
        if "avatar" not in item:
            return item
        cleaned = dict(item)
        del cleaned["avatar"]
        return cleaned

    def add_results(self, items: list[dict]) -> None:
        if not items:
            return
        with self._lock:
            self._state["results"].extend(self._strip_avatar(i) for i in items)

    def set_running(self, is_running: bool) -> None:
        with self._lock:
            self._state["is_running"] = is_running

    def set_monitoring(self, is_monitoring: bool) -> None:
        with self._lock:
            self._state["is_monitoring"] = is_monitoring

    def replace_results(self, items: list[dict]) -> None:
        with self._lock:
            self._state["results"] = [self._strip_avatar(i) for i in items]
