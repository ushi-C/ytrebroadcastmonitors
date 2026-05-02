"""
config_manager.py
─────────────────
窗口配置的持久化（JSON），与其他模块无依赖。
"""

import json
import logging
import os
import tempfile
from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class WindowConfig:
    window_x: int | None = None
    window_y: int | None = None
    window_width: int = 1320
    window_height: int = 860
    zoom_level: float = 1.0


class ConfigManager:
    def __init__(self, config_path: str, logger: logging.Logger):
        self.config_path = config_path
        self.logger = logger

    def load(self) -> WindowConfig:
        if not os.path.exists(self.config_path):
            self.logger.info("Config file does not exist, using defaults: %s", self.config_path)
            return WindowConfig()
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            cfg = WindowConfig(
                window_x=self._to_optional_int(raw.get("window_x")),
                window_y=self._to_optional_int(raw.get("window_y")),
                window_width=self._to_int(raw.get("window_width"), 1320),
                window_height=self._to_int(raw.get("window_height"), 860),
                zoom_level=self._to_float(raw.get("zoom_level"), 1.0),
            )
            self.logger.info("Loaded config from %s: %s", self.config_path, cfg)
            return cfg
        except Exception as exc:
            self.logger.exception("Failed to load config %s, using defaults", self.config_path, exc_info=exc)
            return WindowConfig()

    def save(self, config: WindowConfig) -> None:
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        dir_name = os.path.dirname(self.config_path)
        fd, tmp_path = tempfile.mkstemp(prefix="config_", suffix=".tmp", dir=dir_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(asdict(config), f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, self.config_path)
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
        self.logger.info("Saved config to %s: %s", self.config_path, config)

    @staticmethod
    def _to_int(value: Any, default: int) -> int:
        try:
            result = int(value)
            return result if result > 0 else default
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _to_optional_int(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_float(value: Any, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default
