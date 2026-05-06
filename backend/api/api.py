"""
api.py
──────
FastAPI 路由层，不含任何业务逻辑。
所有实际工作都委托给 scanner / avatar_cache / scan_service 模块。
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..cache import avatar_cache as _ac
from ..services import scan_service as _svc
from backend.api.background_api import make_background_router


def _make_lifespan(app_dir_fn):
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        _ac.load_channel_avatar_cache()
        _ac.start_cleanup_loop()
        try:
            yield
        finally:
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
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 注册 background API（FastAPI 正确方式）
    app.include_router(
        make_background_router(config_manager),
        prefix="/api"
    )

    class CheckRequest(BaseModel):
        query: str
        title: str = ""

    @app.post("/api/check")
    async def check_single(req: CheckRequest):
        q = (req.query or "").strip()
        if not q:
            raise HTTPException(status_code=400, detail="query is required")
        result = await _svc.check_single_channel(q, req.title)
        return {"result": result}

    @app.get("/api/channels")
    def get_channels():
        if not os.path.isdir(app_dir_fn()):
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
        for r in status.get("results", []):
            cid = r.get("id")
            r["avatar"] = _ac.get_cached_avatar(cid) if cid else ""
        return status

    @app.get("/api/avatar")
    def get_avatar(u: str):
        if not u or not u.startswith("http"):
            raise HTTPException(status_code=400, detail="invalid url")
        try:
            path = _ac.get_avatar_disk_path(u)
        except ValueError as exc:
            raise HTTPException(status_code=413, detail="image too large") from exc
        except Exception as exc:
            raise HTTPException(status_code=404, detail="fetch failed") from exc
        return FileResponse(
            path,
            headers={"Cache-Control": "public, max-age=31536000, immutable"}
        )

    # 静态文件必须最后挂载，否则会覆盖 API 路由
    app.mount("/", StaticFiles(directory=resource_dir, html=True), name="static")

    return app
