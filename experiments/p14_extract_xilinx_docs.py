"""Extract text from the Tronlong TLZ7xH-EVM material set for read-only review.

Reads PDFs from D:\\xilinx and writes one .txt per PDF plus an index, so the
review notes can cite line-addressable text instead of re-parsing PDFs.

Read-only with respect to the source material: nothing under D:\\xilinx is
modified. Output goes under tmp/new-board-xilinx-review/.
"""

import json
import sys
from pathlib import Path

from pypdf import PdfReader

SOURCE = Path(r"D:\xilinx\xilinx")
OUT = Path(__file__).resolve().parents[1] / "tmp" / "new-board-xilinx-review"

# Ordered by how much they matter for the questions being answered.
TARGETS = [
    ("1-开箱必读/产品规格书/SOM-TLZ7xH核心板规格书.pdf", "coreboard-spec"),
    ("1-开箱必读/产品规格书/TLZ7xH-EVM评估板规格书.pdf", "evm-spec"),
    ("1-开箱必读/产品规格书/拓展模块规格书/TL070A显示屏规格书.pdf", "lcd-tl070a-spec"),
    ("1-开箱必读/开箱必读.pdf", "open-first-read"),
    ("5-硬件资料/TLZ7xH-EVM评估板硬件说明书.pdf", "evm-hardware-manual"),
    ("5-硬件资料/核心板资料/SOM-TLZ7xH核心板硬件说明书.pdf", "coreboard-hardware-manual"),
    ("3-用户手册/2-1-评估板测试手册.pdf", "evm-test-manual"),
    ("3-用户手册/3-1-Linux系统使用手册.pdf", "linux-usage-manual"),
    ("3-用户手册/2-3-Qt工程编译说明.pdf", "qt-build"),
    ("4-软件资料/Tools/setup-x86_64.exe", None),  # placeholder, skipped (not a pdf)
]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    index = []
    for rel, stem in TARGETS:
        if stem is None:
            continue
        path = SOURCE / rel
        entry = {"source": str(path), "exists": path.is_file()}
        if not path.is_file():
            entry["status"] = "missing"
            index.append(entry)
            print(f"MISSING {rel}")
            continue
        try:
            reader = PdfReader(str(path))
            pages = []
            for number, page in enumerate(reader.pages, start=1):
                try:
                    text = page.extract_text() or ""
                except Exception as exc:                     # noqa: BLE001
                    text = f"<<page {number} extract failed: {exc}>>"
                pages.append(f"\n===== PAGE {number} =====\n{text}")
            body = "".join(pages)
            target = OUT / f"{stem}.txt"
            target.write_text(body, encoding="utf-8")
            chars = len(body.strip())
            entry.update(pages=len(reader.pages), chars=chars,
                         out=str(target.name),
                         status="ok" if chars > 200 else "little_or_no_text_layer")
            print(f"{stem:28s} pages={len(reader.pages):3d} chars={chars:7d} {entry['status']}")
        except Exception as exc:                             # noqa: BLE001
            entry.update(status="error", error=str(exc))
            print(f"{stem:28s} ERROR {exc}")
        index.append(entry)
    (OUT / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nindex: {OUT / 'index.json'}")


if __name__ == "__main__":
    sys.exit(main())
