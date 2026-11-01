"""Read the two numeric columns exported from the P01 IIO capture."""

import csv
from pathlib import Path


csv_path = (
    Path(__file__).resolve().parents[1]
    / "results" / "p01-20260928" / "capture-initial.csv"
)

pairs = []
with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
    for line_number, row in enumerate(csv.reader(file), start=1):
        if not row or all(not cell.strip() for cell in row):
            continue
        if len(row) < 2 or any(cell.strip() for cell in row[2:]):
            raise ValueError(f"第 {line_number} 行格式不符合预期：{row}")
        pairs.append((int(row[0].strip()), int(row[1].strip())))

iq = [complex(i, q) for i, q in pairs]
print("采样对数：", len(iq))
print("第一对 I/Q：", pairs[0])
print("第一个复数样本：", iq[0])
print("最后一对 I/Q：", pairs[-1])
