"""读取 IIO Oscilloscope 导出的 I/Q CSV。"""

import csv
from pathlib import Path

import numpy as np
from numpy.typing import NDArray


def load_iq_csv(path: str | Path) -> NDArray[np.int16]:
    """返回形状为 (样本对数, 2) 的原始有符号整数。"""
    pairs = []

    with Path(path).open("r", encoding="utf-8-sig", newline="") as file:
        for line_number, row in enumerate(csv.reader(file), start=1):
            if not row or all(not cell.strip() for cell in row):
                continue
            if len(row) < 2 or any(cell.strip() for cell in row[2:]):
                raise ValueError(f"第 {line_number} 行列数不正确")

            try:
                i, q = int(row[0].strip()), int(row[1].strip())
            except ValueError as error:
                raise ValueError(f"第 {line_number} 行不是整数") from error

            if not all(-32768 <= value <= 32767 for value in (i, q)):
                raise ValueError(f"第 {line_number} 行超出有符号 16 位范围")
            pairs.append((i, q))

    if not pairs:
        raise ValueError("文件没有 I/Q 样本")
    return np.asarray(pairs, dtype=np.int16)
