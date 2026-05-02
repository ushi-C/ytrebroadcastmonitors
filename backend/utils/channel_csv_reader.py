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
