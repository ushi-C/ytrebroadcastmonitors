"""
background_api.py
─────────────────
背景图片持久化 API（FastAPI 版本）。
挂载到主 FastAPI 应用后提供以下端点：

  PUT    /api/background   上传背景（JSON body: {"data": "<base64 data URL>"})
  GET    /api/background   读取背景（返回 JSON: {"data": "<base64 data URL>"})
  DELETE /api/background   清除背景

图片以原始字节写入磁盘（去掉 data URL 头），路径记录在 WindowConfig.background_path。
这样图片本体与配置解耦，config.json 只存路径，不存图片数据。

使用方式（在 api.py 中）：
    from backend.api.background_api import make_background_router
    app.include_router(make_background_router(config_manager), prefix='/api')
"""

from __future__ import annotations

import base64
import logging
import os
import re
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

if TYPE_CHECKING:
    from backend.utils.config_manager import ConfigManager

logger = logging.getLogger(__name__)

# 支持的图片 MIME 类型白名单
_ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp", "image/gif", "image/avif"}
# 单张背景图最大字节数（解码后），默认 20 MB
_MAX_BYTES = 20 * 1024 * 1024
# 背景文件名（固定名，方便替换）
_BG_FILENAME = "user_background"


class BgBody(BaseModel):
    data: str


def make_background_router(config_manager: "ConfigManager") -> APIRouter:
    """
    工厂函数：接收已初始化的 ConfigManager，返回 FastAPI APIRouter。
    背景图片保存在与 config.json 同目录下。
    """
    router = APIRouter()
    _bg_dir = os.path.dirname(config_manager.config_path)

    def _bg_path(ext: str) -> str:
        return os.path.join(_bg_dir, f"{_BG_FILENAME}.{ext}")

    def _find_existing_bg() -> str | None:
        """返回当前背景文件的完整路径（任意扩展名），不存在返回 None。"""
        cfg = config_manager.load()
        if cfg.background_path and os.path.isfile(cfg.background_path):
            return cfg.background_path

        # 兼容旧版：按扩展名枚举
        for ext in ("jpg", "jpeg", "png", "webp", "gif", "avif"):
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
        }.get(mime, "jpg")

    @router.put("/background")
    async def save_background(body: BgBody):
        """接收 base64 data URL，解码后写入磁盘，路径记入配置。"""
        data_url: str = body.data or ""

        # 解析 data URL
        match = re.match(r"data:(?P<mime>[^;]+);base64,(?P<b64>.+)", data_url, re.DOTALL)
        if not match:
            raise HTTPException(status_code=400, detail="invalid data URL")

        mime = match.group("mime")
        if mime not in _ALLOWED_MIME:
            raise HTTPException(status_code=415, detail=f"unsupported image type: {mime}")

        try:
            raw = base64.b64decode(match.group("b64"))
        except Exception:
            raise HTTPException(status_code=400, detail="base64 decode failed")

        if len(raw) > _MAX_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"image too large (max {_MAX_BYTES // 1024 // 1024} MB)",
            )

        ext = _mime_to_ext(mime)
        save_path = _bg_path(ext)

        # 删除旧文件（可能扩展名不同）
        old = _find_existing_bg()
        if old and old != save_path:
            try:
                os.remove(old)
            except OSError:
                pass

        os.makedirs(_bg_dir, exist_ok=True)
        with open(save_path, "wb") as f:
            f.write(raw)

        # 更新配置中的路径
        cfg = config_manager.load()
        cfg.background_path = save_path
        config_manager.save(cfg)

        logger.info("Background saved to %s (%d bytes)", save_path, len(raw))
        return {"ok": True, "path": save_path}

    @router.get("/background")
    async def load_background():
        """读取背景文件，返回 base64 data URL；无背景时返回 404。"""
        bg_path = _find_existing_bg()
        if not bg_path:
            raise HTTPException(status_code=404, detail="no background set")

        ext = os.path.splitext(bg_path)[1].lstrip(".")
        mime = {
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "webp": "image/webp",
            "gif": "image/gif",
            "avif": "image/avif",
        }.get(ext, "image/jpeg")

        try:
            with open(bg_path, "rb") as f:
                raw = f.read()
        except OSError as exc:
            logger.error("Failed to read background: %s", exc)
            raise HTTPException(status_code=500, detail="read failed")

        b64 = base64.b64encode(raw).decode()
        data_url = f"data:{mime};base64,{b64}"
        return {"data": data_url}

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
