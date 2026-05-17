from __future__ import annotations

import threading
import time
from copy import deepcopy


class NetworkStateStore:
    """线程安全的 YouTube 网络可用性状态存储。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._state = {
            "youtube_available": False,
            "reason": "UNTESTED",
            "last_check": 0,
            "check_requested": False,
        }

    def get_snapshot(self) -> dict:
        with self._lock:
            return deepcopy(self._state)

    def report(self, youtube_available: bool, reason: str) -> dict:
        with self._lock:
            self._state["youtube_available"] = bool(youtube_available)
            self._state["reason"] = (reason or "UNKNOWN").strip() or "UNKNOWN"
            self._state["last_check"] = int(time.time())
            self._state["check_requested"] = False
            return deepcopy(self._state)

    def request_check(self) -> dict:
        with self._lock:
            self._state["check_requested"] = True
            return deepcopy(self._state)

    def consume_check_request(self) -> bool:
        with self._lock:
            requested = bool(self._state.get("check_requested"))
            self._state["check_requested"] = False
            return requested
