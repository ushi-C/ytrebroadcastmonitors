"""
api.py
──────
FastAPI 路由层，不含任何业务逻辑。
所有实际工作都委托给 scanner / avatar_cache / scan_service 模块。
"""

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..cache import avatar_cache as _ac
from ..services import scan_service as _svc
from ..utils.channel_csv_reader import resolve_channels_dir
from ..services import youtube_probe as _yt_probe
from ..websocket.manager import ws_manager, broadcast_scan_status
from .background_api import make_background_router


def _make_lifespan(app_dir_fn):
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        # ── 注入 WS 广播回调到 avatar_cache ──
        # 头像缓存更新后，通过 run_coroutine_threadsafe 触发 WS 广播
        loop = asyncio.get_running_loop()

        def _trigger_broadcast():
            if loop.is_running():
                asyncio.run_coroutine_threadsafe(broadcast_scan_status(), loop)

        _ac.set_broadcast_fn(_trigger_broadcast)

        _ac.load_channel_avatar_cache()
        _ac.start_cleanup_loop()
        _ac.start_flush_loop()  # 启动定时刷盘线程
        try:
            yield
        finally:
            _ac.flush()  # 退出时强制刷盘
            _ac.save_channel_avatar_cache()
    return lifespan


def build_app(resource_dir: str, app_dir_fn, config_manager) -> FastAPI:
    """
    创建并返回配置好的 FastAPI 实例。

    Parameters
    ----------
    resource_dir : str       打包后的资源根目录（存放 index.html 等静态文件）
    app_dir_fn   : callable  返回运行时数据目录的函数
    config_manager : ConfigManager  配置管理器（用于 background API）
    """
    app = FastAPI(lifespan=_make_lifespan(app_dir_fn))

    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=(
            r'^https?://(?:localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\]|'
            r'10\.\d{1,3}\.\d{1,3}\.\d{1,3}|'
            r'172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}|'
            r'192\.168\.\d{1,3}\.\d{1,3})'
            r'(?::\d+)?$'
        ),
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 背景/视频上传目录（挂载为 /static，支持 HTTP Range 流式加载）
    uploads_dir = os.path.join(app_dir_fn(), "uploads")
    os.makedirs(uploads_dir, exist_ok=True)

    # 注册 background API（FastAPI 正确方式）
    app.include_router(
        make_background_router(config_manager, uploads_dir),
        prefix="/api"
    )

    # /static 必须在 / 之前挂载，否则会被 catch-all 覆盖
    app.mount("/static", StaticFiles(directory=uploads_dir), name="uploads")

    class CheckRequest(BaseModel):
        query: str
        title: str = ""

    class NetworkReportRequest(BaseModel):
        youtube_available: bool
        reason: str = "UNKNOWN"

    @app.get("/api/network/status")
    async def get_network_status():
        return _yt_probe.get_network_status()

    @app.post("/api/network/report")
    async def report_network_status(req: NetworkReportRequest):
        return _yt_probe.report_network_status(req.youtube_available, req.reason)

    @app.post("/api/network/check")
    async def request_network_check():
        return _yt_probe.request_network_check()

    @app.post("/api/check")
    async def check_single(req: CheckRequest):
        q = (req.query or "").strip()
        if not q:
            raise HTTPException(status_code=400, detail="query is required")
        result = await _svc.check_single_channel(q, req.title)
        return {"result": result}

    @app.get("/api/channels")
    def get_channels():
        if not resolve_channels_dir(app_dir_fn()):
            return {"channels": []}
        return {"channels": _svc.load_channels_for_search(app_dir_fn)}

    @app.post("/api/refresh")
    async def trigger_refresh():
        return {"status": await _svc.trigger_refresh_scan()}

    @app.get("/api/status")
    async def get_status():
        # ── Single Writer Principle ────────────────────────────────────────────
        # ScanStateStore 是唯一写入口；results 中不存储 avatar。
        # avatar 在此处从缓存派生并注入响应副本（get_scan_status 返回深拷贝），
        # 不回写 state，monitor 轮次对头像无任何影响。
        status = _svc.get_scan_status()  # deep-copy snapshot, safe to mutate
        results = status.get("results", [])
        for r in results:
            cid = r.get("id")
            r["avatar"] = _ac.get_cached_avatar(cid) if cid else ""
        # 缺头像时由 status 轮询触发补抓；innertube 写入缓存后下一轮即可注入 card
        await _svc.schedule_missing_avatar_fetches(results)
        return status

    @app.get("/api/avatar")
    def get_avatar(u: str):
        if not u or not u.startswith("http"):
            raise HTTPException(status_code=400, detail="invalid url")
        try:
            path = _ac.get_avatar_disk_path(u)
        except ValueError as exc:
            msg = str(exc).lower()
            # 域名/IP 拦截 → 403；文件过大 → 413；其余 → 404
            if "domain not allowed" in msg or "blocked" in msg or "private ip" in msg:
                raise HTTPException(status_code=403, detail=str(exc)) from exc
            if "too large" in msg:
                raise HTTPException(status_code=413, detail="image too large") from exc
            raise HTTPException(status_code=404, detail="fetch failed") from exc
        except Exception as exc:
            raise HTTPException(status_code=404, detail="fetch failed") from exc
        return FileResponse(
            path,
            headers={"Cache-Control": "public, max-age=31536000, immutable"}
        )

    # ── WebSocket 状态推送 ────────────────────────────────────────────────────
    @app.websocket("/api/ws/status")
    async def ws_status(ws: WebSocket):
        await ws_manager.connect(ws)
        try:
            # 连接建立时推送当前完整状态
            await broadcast_scan_status()
            # 保持连接，处理心跳
            while True:
                try:
                    msg = await ws.receive_text()
                    if msg == "ping":
                        await ws.send_text("pong")
                except WebSocketDisconnect:
                    break
        except WebSocketDisconnect:
            pass
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("[ws] unexpected error: %s", exc)
        finally:
            ws_manager.disconnect(ws)

    # 静态文件必须最后挂载，否则会覆盖 API 路由
    app.mount("/", StaticFiles(directory=resource_dir, html=True), name="static")

    return app
