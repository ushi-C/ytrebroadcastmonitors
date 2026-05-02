"""
scan_state_store.py
───────────────────
扫描状态存储（线程安全）。
"""

from __future__ import annotations

from threading import RLock
from typing import Any


class ScanStateStore:
    """对扫描状态字典进行受控读写。"""

    def __init__(self) -> None:
        self._lock = RLock()
        self._state: dict[str, Any] = {
            "is_running": False,
            "progress": 0,
            "total": 0,
            "results": [],
        }

    @property
    def state(self) -> dict[str, Any]:
        """返回状态字典引用（供外部只读访问）。"""
        return self._state

    @property
    def is_running(self) -> bool:
        return self._state["is_running"]

    def reset_for_new_scan(self) -> None:
        with self._lock:
            self._state.update(is_running=True, progress=0, total=0, results=[])

    def set_total(self, total: int) -> None:
        with self._lock:
            self._state["total"] = total

    def add_progress(self, count: int) -> None:
        with self._lock:
            self._state["progress"] += count

    def add_results(self, items: list[dict]) -> None:
        if not items:
            return
        with self._lock:
            self._state["results"].extend(items)

    def set_running(self, is_running: bool) -> None:
        with self._lock:
            self._state["is_running"] = is_running
