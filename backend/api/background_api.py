"""
background_api.py
─────────────────
背景图片/视频持久化 API（FastAPI 版本）。
挂载到主 FastAPI 应用后提供以下端点：

  PUT    /api/background   上传背景（multipart/form-data: file=@图片文件）
  GET    /api/background   获取背景元信息（JSON: {"url": "/static/...", "path": "..."}）
  GET    /static/...       流式读取背景文件（StaticFiles 挂载，天然支持 HTTP Range）
  DELETE /api/background   清除背景

图片以原始字节流写入本地 uploads/ 目录（shutil.copyfileobj 边读边写），
不再经过 Base64 编解码，内存开销恒定。路径记录在 WindowConfig.background_path。

未来扩展：
  - 支持 video/mp4、video/webm 动态视频背景
  - StaticFiles 内建 HTTP Range 分片，前端 <video> 可直接流式播放

使用方式（在 api.py 中）：
    from backend.api.background_api import make_background_router
    app.include_router(make_background_router(config_manager, uploads_dir), prefix='/api')
"""

from __future__ import annotations

import logging
import os
import shutil
from typing import TYPE_CHECKING

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

if TYPE_CHECKING:
    from backend.utils.config_manager import ConfigManager

logger = logging.getLogger(__name__)

# 支持的 MIME 类型白名单（图片 + 视频扩展）
_ALLOWED_MIME = {
    "image/jpeg", "image/png", "image/webp", "image/gif", "image/avif",
    "video/mp4", "video/webm",
}
# 单张背景图最大字节数，默认 50 MB（含视频）
_MAX_BYTES = 50 * 1024 * 1024
# 背景文件名（固定名，方便替换）
_BG_FILENAME = "user_background"


def make_background_router(config_manager: "ConfigManager", uploads_dir: str) -> APIRouter:
    """
    工厂函数：接收已初始化的 ConfigManager 和 uploads 目录，返回 FastAPI APIRouter。
    背景文件保存在 uploads_dir 目录下，通过 /static/ 前缀对外暴露。
    """
    router = APIRouter()

    # 确保 uploads 目录存在
    os.makedirs(uploads_dir, exist_ok=True)

    def _bg_path(ext: str) -> str:
        return os.path.join(uploads_dir, f"{_BG_FILENAME}.{ext}")

    def _find_existing_bg() -> str | None:
        """返回当前背景文件的完整路径（任意扩展名），不存在返回 None。"""
        cfg = config_manager.load()
        if cfg.background_path and os.path.isfile(cfg.background_path):
            return cfg.background_path

        # 兼容旧版：按扩展名枚举
        for ext in ("jpg", "jpeg", "png", "webp", "gif", "avif", "mp4", "webm"):
            p = _bg_path(ext)
            if os.path.isfile(p):
                return p
        return None

    def _mime_to_ext(mime: str) -> str:
        return {
            "image/jpeg": "jpg",
            "image/png": "png",
            "image/webp": "webp",
            "image/gif": "gif",
            "image/avif": "avif",
            "video/mp4": "mp4",
            "video/webm": "webm",
        }.get(mime, "jpg")

    def _url_for(path: str) -> str:
        """根据文件路径生成静态 URL。"""
        ext = os.path.splitext(path)[1].lstrip(".")
        return f"/static/{_BG_FILENAME}.{ext}"

    @router.put("/background")
    async def save_background(file: UploadFile = File(...)):
        """接收 multipart/form-data 上传，流式写入 uploads/ 目录。

        与旧版 Base64 JSON 不同：
        - 前端使用 FormData + <input type="file">
        - 后端 shutil.copyfileobj 边读边写，不占内存
        - 支持图片和视频文件
        """
        mime = (file.content_type or "").lower()
        if mime not in _ALLOWED_MIME:
            raise HTTPException(status_code=415, detail=f"unsupported media type: {mime}")

        ext = _mime_to_ext(mime)
        save_path = _bg_path(ext)

        # 删除旧文件（可能扩展名不同）
        old = _find_existing_bg()
        if old and os.path.abspath(old) != os.path.abspath(save_path):
            try:
                os.remove(old)
            except OSError:
                pass

        # ── 流式写入：边读边写，内存占用恒定 ──
        try:
            with open(save_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
        except Exception as exc:
            # 写入失败则清理残留
            if os.path.exists(save_path):
                try:
                    os.remove(save_path)
                except OSError:
                    pass
            raise HTTPException(status_code=500, detail=f"write failed: {exc}") from exc
        finally:
            file.file.close()

        # ── 大小校验 ──
        file_size = os.path.getsize(save_path)
        if file_size > _MAX_BYTES:
            try:
                os.remove(save_path)
            except OSError:
                pass
            raise HTTPException(
                status_code=413,
                detail=f"file too large (max {_MAX_BYTES // 1024 // 1024} MB)",
            )

        # ── 更新配置中的路径 ──
        cfg = config_manager.load()
        cfg.background_path = save_path
        config_manager.save(cfg)

        static_url = _url_for(save_path)
        logger.info("Background saved: %s → %s (%d bytes)", mime, save_path, file_size)
        return {"ok": True, "url": static_url, "path": save_path}

    @router.get("/background")
    async def load_background():
        """返回背景文件元信息；无背景时返回 404。

        响应示例：
            {"ok": true, "url": "/static/user_background.jpg", "path": "..."}

        前端直接用返回的 url 设置背景（<img> 或 CSS background-image），
        不再需要 Base64 编解码。
        """
        bg_path = _find_existing_bg()
        if not bg_path:
            raise HTTPException(status_code=404, detail="no background set")

        static_url = _url_for(bg_path)

        # 若路径在旧 config 目录（迁移），则无法通过 /static 访问
        if not os.path.abspath(bg_path).startswith(os.path.abspath(uploads_dir)):
            logger.warning(
                "Background file outside uploads dir (legacy): %s, "
                "will serve via FileResponse directly",
                bg_path,
            )
            return FileResponse(bg_path)

        return {"ok": True, "url": static_url, "path": bg_path}

    @router.delete("/background")
    async def delete_background():
        """删除背景文件并清除配置中的路径。"""
        bg_path = _find_existing_bg()
        if bg_path:
            try:
                os.remove(bg_path)
                logger.info("Background deleted: %s", bg_path)
            except OSError as exc:
                logger.warning("Failed to delete background file: %s", exc)

        cfg = config_manager.load()
        cfg.background_path = ""
        config_manager.save(cfg)

        return {"ok": True}

    return router
