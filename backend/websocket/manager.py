"""
websocket/manager.py
────────────────────
WebSocket 连接管理器 + 状态广播。

- WSManager: 管理活跃连接池，支持 broadcast
- broadcast_scan_status(): 构建带 avatar 的状态快照并推送所有客户端
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger("YVmonitor")


class WSManager:
    """管理 WebSocket 活跃连接池。"""

    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.add(ws)
        logger.info("[ws] client connected, total=%d", len(self._connections))

    def disconnect(self, ws: WebSocket) -> None:
        self._connections.discard(ws)
        logger.info("[ws] client disconnected, total=%d", len(self._connections))

    async def broadcast(self, data: dict[str, Any]) -> None:
        """向所有活跃连接广播 JSON 数据。自动清理断开的连接。"""
        if not self._connections:
            return
        dead: list[WebSocket] = []
        for ws in list(self._connections):
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections.discard(ws)

    @property
    def connection_count(self) -> int:
        return len(self._connections)


ws_manager = WSManager()


async def broadcast_scan_status() -> None:
    """
    构建当前扫描状态快照（含 avatar 派生字段）并广播给所有 WS 客户端。

    由 scanner.py 在状态变更后调用，也可由 avatar_cache 通过
    asyncio.run_coroutine_threadsafe 间接触发。
    """
    if ws_manager.connection_count == 0:
        return

    from ..cache import avatar_cache as _ac
    from ..services import scanner as _sc

    snapshot = _sc.SCAN_STATE_STORE.get_snapshot()
    for r in snapshot.get("results", []):
        cid = r.get("id")
        r["avatar"] = _ac.get_cached_avatar(cid) if cid else ""

    await ws_manager.broadcast({"type": "status", "data": snapshot})
