"""Extract the embedded figures from the TLZ7xH-EVM manuals.

The manuals ship photos of the assembled board and numbered connector diagrams.
Extracting them lets the operator see the exact connector rather than reading a
text description, without re-scanning or re-photographing anything.

Read-only on D:\\xilinx. Output goes to tmp/new-board-xilinx-review/figures/.
"""

import json
from pathlib import Path

from pypdf import PdfReader

SOURCE = Path(r"D:\xilinx\xilinx")
OUT = Path(__file__).resolve().parents[1] / "tmp" / "new-board-xilinx-review" / "figures"

# (pdf, stem, pages to pull figures from)  -- 1-based page numbers
TARGETS = [
    ("1-开箱必读/开箱必读.pdf", "open-first-read", [3, 4]),
    ("5-硬件资料/TLZ7xH-EVM评估板硬件说明书.pdf", "evm-hardware", [4, 5, 6, 7, 8, 9, 10, 11, 12]),
    ("1-开箱必读/产品规格书/TLZ7xH-EVM评估板规格书.pdf", "evm-spec", [5, 6, 8]),
    ("1-开箱必读/产品规格书/拓展模块规格书/TL070A显示屏规格书.pdf", "lcd", [3, 4]),
]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    index = []
    for rel, stem, pages in TARGETS:
        path = SOURCE / rel
        if not path.is_file():
            print(f"MISSING {rel}")
            continue
        reader = PdfReader(str(path))
        for page_no in pages:
            if page_no > len(reader.pages):
                continue
            page = reader.pages[page_no - 1]
            try:
                images = list(page.images)
            except Exception as exc:                       # noqa: BLE001
                print(f"{stem} p{page_no}: image read failed {exc}")
                continue
            for n, image in enumerate(images):
                # Skip tiny inline artifacts (logos, rules).
                data = image.data
                if len(data) < 20_000:
                    continue
                name = image.name or f"img{n}"
                suffix = Path(name).suffix or ".png"
                target = OUT / f"{stem}-p{page_no:02d}-{n}{suffix}"
                target.write_bytes(data)
                index.append({"pdf": rel, "page": page_no, "file": target.name,
                              "bytes": len(data), "source_name": name})
                print(f"{stem:16s} p{page_no:02d} -> {target.name:44s} {len(data):>9,} B")
    (OUT / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n",
                                    encoding="utf-8")
    print(f"\n{len(index)} figures -> {OUT}")


if __name__ == "__main__":
    main()
