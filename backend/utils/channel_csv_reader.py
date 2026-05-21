"""
channel_csv_reader.py
─────────────────────
统一 channels.csv 读取策略：
- 按既定编码顺序尝试读取
- 将字段名标准化为小写并去除空白
- 读取失败时返回空列表
"""

from __future__ import annotations

import csv
import os
from typing import Iterable

CHANNELS_CSV_ENCODINGS: tuple[str, ...] = (
    "utf-8-sig",
    "gbk",
    "cp936",
    "cp932",
    "shift_jis",
    "utf-8",
    "latin1",
)


def read_channels_csv_rows(file_path: str, encodings: Iterable[str] = CHANNELS_CSV_ENCODINGS) -> list[dict]:
    """读取 channels.csv 并返回原始行列表。全部编码失败时返回 []。"""
    for encoding in encodings:
        try:
            with open(file_path, mode="r", encoding=encoding) as f:
                reader = csv.DictReader(f)
                # 触发首行读取后再标准化字段名，避免空文件时把首行当数据行
                fieldnames = reader.fieldnames
                if fieldnames:
                    reader.fieldnames = [fn.lower().strip() for fn in fieldnames]
                return list(reader)
        except Exception:
            continue
    return []


def resolve_channels_dir(app_dir: str) -> str | None:
    """定位频道 CSV 目录。安装包为 {app}/channels；开发时 app_dir 常为 backend/。"""
    candidates: list[str] = [os.path.join(app_dir, "channels")]

    if os.path.basename(os.path.normpath(app_dir)) == "backend":
        candidates.append(os.path.join(os.path.dirname(app_dir), "channels"))

    # 兼容旧布局：CSV 直接放在 app_dir 下
    candidates.append(app_dir)

    seen: set[str] = set()
    for path in candidates:
        norm = os.path.normpath(path)
        if norm in seen:
            continue
        seen.add(norm)
        if os.path.isdir(norm):
            return norm
    return None


def read_all_csv_rows_in_dir(dir_path: str) -> list[dict]:
    """读取目录下全部 .csv 文件并合并。"""
    if not os.path.isdir(dir_path):
        return []

    rows: list[dict] = []
    for name in sorted(os.listdir(dir_path)):
        if not name.lower().endswith(".csv"):
            continue
        file_path = os.path.join(dir_path, name)
        if not os.path.isfile(file_path):
            continue
        rows.extend(read_channels_csv_rows(file_path))
    return rows
