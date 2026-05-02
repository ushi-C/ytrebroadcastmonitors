"""
main.py
───────
应用入口：日志初始化、服务器启动、WebView2 GUI。
业务逻辑全部在 scanner / avatar_cache / api / config_manager 中。
"""

import argparse
import inspect
import logging
import os
import socket
import sys
import threading
import time
import webbrowser
from logging.handlers import RotatingFileHandler

import uvicorn
import webview

from backend.utils.config_manager import ConfigManager, WindowConfig
from backend.cache import avatar_cache as _ac
from backend.services import scanner as _sc
from backend.api.api import build_app


# ── 路径工具 ──────────────────────────────────────────────────────────────────

def _resource_dir() -> str:
    """打包后返回 _MEIPASS，开发时返回脚本所在目录。"""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS  # type: ignore[attr-defined]
    return os.path.dirname(os.path.abspath(__file__))


def _app_dir() -> str:
    """运行时数据目录：打包后为 exe 所在目录，开发时为脚本目录。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


# ── 日志 ──────────────────────────────────────────────────────────────────────

def _setup_logger() -> logging.Logger:
    logger = logging.getLogger("YVmonitor")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    log_path = os.path.join(_app_dir(), "app.log")
    handler = RotatingFileHandler(log_path, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.info("Logger initialized: %s", log_path)
    return logger


LOGGER = _setup_logger()


# ── 全局 FastAPI 应用（供 uvicorn 使用）──────────────────────────────────────

# 初始化各模块（注入依赖）
_ac.init(
    logger=LOGGER,
    cache_file=os.path.join(_app_dir(), "channel_avatar_cache.json"),
    cache_dir=os.path.join(_app_dir(), "avatar_cache"),
    scan_state=_sc.SCAN_STATE,
)
_sc.init(logger=LOGGER, app_dir_fn=_app_dir)

app = build_app(
    resource_dir=os.path.join(_resource_dir(), "static"),
    app_dir_fn=_app_dir
)


# ── 服务器 ────────────────────────────────────────────────────────────────────

def _run_server(host: str, port: int) -> None:
    uvicorn.run(app, host=host, port=port, log_level="warning")


def _wait_server_ready(host: str, port: int, timeout_sec: float = 15.0) -> bool:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.3)
            if s.connect_ex((host, port)) == 0:
                return True
        time.sleep(0.2)
    return False


# ── 窗口位置工具 ──────────────────────────────────────────────────────────────

def _get_virtual_screen_rect() -> tuple[int, int, int, int] | None:
    if os.name != "nt":
        return None
    try:
        import ctypes
        u32    = ctypes.windll.user32
        left   = u32.GetSystemMetrics(76)
        top    = u32.GetSystemMetrics(77)
        width  = u32.GetSystemMetrics(78)
        height = u32.GetSystemMetrics(79)
        if width > 0 and height > 0:
            return left, top, width, height
    except Exception as exc:
        LOGGER.warning("Failed to get virtual screen metrics: %s", exc)
    return None


def _get_centered_position(width: int, height: int) -> tuple[int, int]:
    rect = _get_virtual_screen_rect()
    if not rect:
        return 50, 50
    left, top, screen_w, screen_h = rect
    return left + max(0, (screen_w - width) // 2), top + max(0, (screen_h - height) // 2)


def _is_window_visible(x: int, y: int, width: int, height: int, rect: tuple) -> bool:
    left, top, screen_w, screen_h = rect
    right  = left + screen_w
    bottom = top  + screen_h
    margin = 80
    return (
        (x + margin) < right
        and (x + width - margin) > left
        and (y + margin) < bottom
        and (y + height - margin) > top
    )


def _sanitize_window_config(config: WindowConfig) -> WindowConfig:
    width  = max(980, int(config.window_width))
    height = max(680, int(config.window_height))
    x, y   = config.window_x, config.window_y
    rect   = _get_virtual_screen_rect()
    if rect and x is not None and y is not None:
        left, top, screen_w, screen_h = rect
        width  = min(width,  screen_w)
        height = min(height, screen_h)
        if not _is_window_visible(x, y, width, height, rect):
            x, y = _get_centered_position(width, height)
            LOGGER.info("Window position out of bounds, reset to center: (%s, %s)", x, y)
        else:
            LOGGER.info("Window position validated: (%s, %s, %s, %s)", x, y, width, height)
    else:
        x, y = _get_centered_position(width, height)
        LOGGER.info("Window position missing or no screen bounds, use center: (%s, %s)", x, y)
    return WindowConfig(window_x=x, window_y=y, window_width=width, window_height=height, zoom_level=config.zoom_level)


# ── WebView2 GUI ──────────────────────────────────────────────────────────────

def _run_gui(url: str, cfg_manager: ConfigManager) -> None:
    cfg    = _sanitize_window_config(cfg_manager.load())
    window = webview.create_window(
        "YVmonitor",
        url=url,
        width=cfg.window_width,
        height=cfg.window_height,
        min_size=(980, 680),
        x=cfg.window_x,
        y=cfg.window_y,
    )

    def _on_closing():
        try:
            x, y   = int(window.x), int(window.y)
            width  = int(window.width)
            height = int(window.height)
            rect   = _get_virtual_screen_rect()
            if rect:
                left, top, screen_w, screen_h = rect
                width  = min(max(980, width),  screen_w)
                height = min(max(680, height), screen_h)
                x = max(left - width  + 80, min(x, left + screen_w - 80))
                y = max(top  - height + 80, min(y, top  + screen_h - 80))
            cfg_manager.save(WindowConfig(
                window_x=x, window_y=y,
                window_width=width, window_height=height,
                zoom_level=cfg.zoom_level,
            ))
            LOGGER.info("Window closing config saved.")
        except Exception as exc:
            LOGGER.exception("Failed saving window config before close.", exc_info=exc)
        return True

    def _on_loaded():
        try:
            if cfg.zoom_level and cfg.zoom_level > 0 and cfg.zoom_level != 1.0:
                window.evaluate_js(f"document.body.style.zoom = '{cfg.zoom_level}';")
                LOGGER.info("Applied zoom_level=%s", cfg.zoom_level)
        except Exception as exc:
            LOGGER.exception("Failed to apply zoom level.", exc_info=exc)

    window.events.closing += _on_closing
    window.events.loaded  += _on_loaded

    storage_path = os.path.join(_app_dir(), "webview_data")
    os.makedirs(storage_path, exist_ok=True)
    LOGGER.info("Launching WebView2 with data dir=%s", storage_path)

    start_kwargs: dict = {"gui": "edgechromium", "debug": False, "user_agent": None}
    params = inspect.signature(webview.start).parameters
    if "user_data_dir" in params:
        start_kwargs["user_data_dir"] = storage_path
    else:
        start_kwargs["storage_path"] = storage_path

    try:
        webview.start(**start_kwargs)
    except Exception as exc:
        LOGGER.exception("WebView2 initialization failed.", exc_info=exc)
        raise RuntimeError(
            "WebView2 initialization failed. "
            "Please install/update Microsoft Edge WebView2 Runtime."
        ) from exc


# ── 入口 ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="YVmonitor 桌面版")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--mode", choices=["gui", "browser"], default="gui")
    args = parser.parse_args()

    if getattr(sys, "frozen", False) and args.mode == "browser":
        LOGGER.warning("Frozen executable does not allow --mode browser, force gui mode")
        args.mode = "gui"

    LOGGER.info("Application startup: host=%s port=%s mode=%s", args.host, args.port, args.mode)
    LOGGER.info("argv=%s", sys.argv)

    cfg_manager = ConfigManager(os.path.join(_app_dir(), "config.json"), LOGGER)

    server_thread = threading.Thread(target=_run_server, args=(args.host, args.port), daemon=True)
    server_thread.start()

    if not _wait_server_ready(args.host, args.port):
        LOGGER.error("Server failed to start: http://%s:%s", args.host, args.port)
        raise RuntimeError(f"Server failed to start: http://{args.host}:{args.port}")

    app_url = f"http://{args.host}:{args.port}/"
    if args.mode == "browser":
        webbrowser.open(app_url)
        server_thread.join()
        return

    _run_gui(app_url, cfg_manager)


if __name__ == "__main__":
    main()
