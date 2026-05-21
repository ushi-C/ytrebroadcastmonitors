"""
main.py
───────
应用入口：日志初始化、服务器启动、WebView2 GUI。
业务逻辑全部在 scanner / avatar_cache / api / config_manager 中。
"""

import argparse
import base64
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


# ── 服务器 ────────────────────────────────────────────────────────────────────

def _run_server(app, host: str, port: int) -> None:
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
        u32 = ctypes.windll.user32
        left = u32.GetSystemMetrics(76)
        top = u32.GetSystemMetrics(77)
        width = u32.GetSystemMetrics(78)
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
    right = left + screen_w
    bottom = top + screen_h
    margin = 80
    return (
        (x + margin) < right
        and (x + width - margin) > left
        and (y + margin) < bottom
        and (y + height - margin) > top
    )


def _sanitize_window_config(config: WindowConfig) -> WindowConfig:
    width = max(980, int(config.window_width))
    height = max(680, int(config.window_height))
    x, y = config.window_x, config.window_y
    rect = _get_virtual_screen_rect()
    if rect and x is not None and y is not None:
        left, top, screen_w, screen_h = rect
        width = min(width, screen_w)
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
    cfg = _sanitize_window_config(cfg_manager.load())
    splash_closed = False
    ready_signaled = False
    switch_lock = threading.Lock()

    splash_logo_svg = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 800">
  <defs>
    <linearGradient x1="50%" y1="0%" x2="50%" y2="100%" id="nnneon-grad">
      <stop stop-color="hsl(157, 100%, 54%)" offset="0%"/>
      <stop stop-color="hsl(331, 87%, 61%)" offset="100%"/>
    </linearGradient>
    <filter id="nnneon-filter" x="-100%" y="-100%" width="400%" height="400%">
      <feGaussianBlur stdDeviation="17 8"/>
    </filter>
    <filter id="nnneon-filter2" x="-100%" y="-100%" width="400%" height="400%">
      <feGaussianBlur stdDeviation="10 17"/>
    </filter>
  </defs>
  <g stroke-width="16" stroke="url(#nnneon-grad)" fill="none" transform="rotate(90, 400, 400)">
    <polygon points="400,50 50,750 750,750" filter="url(#nnneon-filter)"/>
    <polygon points="412,50 62,750 762,750" filter="url(#nnneon-filter2)" opacity="0.25"/>
    <polygon points="388,50 38,750 738,750" filter="url(#nnneon-filter2)" opacity="0.25"/>
    <polygon points="400,50 50,750 750,750"/>
  </g>
</svg>
""".strip()
    splash_logo_b64 = base64.b64encode(splash_logo_svg.encode("utf-8")).decode("ascii")
    splash_html = f"""<!doctype html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Loading</title>
<style>
  html, body {{ margin: 0; width: 100%; height: 100%; background: transparent; overflow: hidden; }}
  body {{ display: flex; align-items: center; justify-content: center; }}
  .logo-wrap {{ width: 280px; height: 280px; display: flex; align-items: center; justify-content: center; border-radius: 72px; }}
</style></head>
<body><div class="logo-wrap"><img class="logo" src="data:image/svg+xml;base64,{splash_logo_b64}" alt="loading logo"></div></body></html>
"""
    splash_width = 320
    splash_height = 320
    splash_x, splash_y = _get_centered_position(splash_width, splash_height)

    class _JsApi:
        def notify_ready(self):
            nonlocal splash_closed, ready_signaled
            with switch_lock:
                ready_signaled = True
                if splash_closed:
                    return {"ok": True, "already": True}
                try:
                    main_window.show()
                    splash_window.destroy()
                    splash_closed = True
                    LOGGER.info("Startup splash closed by frontend ready signal.")
                    return {"ok": True}
                except Exception as exc:
                    LOGGER.exception("Failed to switch to main window after ready signal.", exc_info=exc)
                    return {"ok": False, "error": str(exc)}

        def toggle_native_fullscreen(self):
            try:
                main_window.toggle_fullscreen()
                return {"ok": True}
            except Exception as exc:
                LOGGER.exception("toggle_native_fullscreen failed", exc_info=exc)
                return {"ok": False, "error": str(exc)}

    js_api = _JsApi()

    splash_window = webview.create_window(
        "YVmonitor Loading",
        html=splash_html,
        width=splash_width,
        height=splash_height,
        min_size=(splash_width, splash_height),
        x=splash_x,
        y=splash_y,
        frameless=True,
        transparent=True,
        on_top=True,
    )

    main_window = webview.create_window(
        "YVmonitor",
        url=url,
        width=cfg.window_width,
        height=cfg.window_height,
        min_size=(980, 680),
        x=cfg.window_x,
        y=cfg.window_y,
        js_api=js_api,
        hidden=True,
    )

    def _on_closing():
        try:
            x, y = int(main_window.x), int(main_window.y)
            width = int(main_window.width)
            height = int(main_window.height)
            rect = _get_virtual_screen_rect()
            if rect:
                left, top, screen_w, screen_h = rect
                width = min(max(980, width), screen_w)
                height = min(max(680, height), screen_h)
                x = max(left - width + 80, min(x, left + screen_w - 80))
                y = max(top - height + 80, min(y, top + screen_h - 80))
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
                main_window.evaluate_js(f"document.body.style.zoom = '{cfg.zoom_level}';")
                LOGGER.info("Applied zoom_level=%s", cfg.zoom_level)
        except Exception as exc:
            LOGGER.exception("Failed to apply zoom level.", exc_info=exc)

    main_window.events.closing += _on_closing
    main_window.events.loaded += _on_loaded

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
        def _startup_timeout() -> None:
            nonlocal splash_closed
            time.sleep(10)
            with switch_lock:
                if splash_closed or ready_signaled:
                    return
                try:
                    main_window.show()
                    splash_window.destroy()
                    splash_closed = True
                    LOGGER.warning("Startup ready signal timeout(10s), forced main window show.")
                except Exception as exc:
                    LOGGER.exception("Failed to force show main window after startup timeout.", exc_info=exc)

        threading.Thread(target=_startup_timeout, daemon=True).start()
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

    LOGGER.info("Application startup: host=%s port=%s mode=%s", args.host, args.port, args.mode)

    cfg_manager = ConfigManager(os.path.join(_app_dir(), "config.json"), LOGGER)

    # 初始化依赖
    _ac.init(
        logger=LOGGER,
        cache_file=os.path.join(_app_dir(), "channel_avatar_cache.json"),
        cache_dir=os.path.join(_app_dir(), "avatar_cache"),
    )
    _sc.init(logger=LOGGER, app_dir_fn=_app_dir)

    # ✅ 正确创建 FastAPI app（传入 config_manager）
    app = build_app(
        resource_dir=os.path.join(_resource_dir(), "static"),
        app_dir_fn=_app_dir,
        config_manager=cfg_manager,
    )

    server_thread = threading.Thread(target=_run_server, args=(app, args.host, args.port), daemon=True)
    server_thread.start()

    if not _wait_server_ready(args.host, args.port):
        raise RuntimeError("Server failed to start")

    url = f"http://{args.host}:{args.port}/"

    if args.mode == "browser":
        webbrowser.open(url)
        server_thread.join()
        return

    _run_gui(url, cfg_manager)


if __name__ == "__main__":
    main()
