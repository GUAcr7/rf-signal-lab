"""Search the evaluation-board schematic PDF for how the FAN header is driven.

The board spec says only "FAN 1x FAN, 3pin, 12V supply". Whether that means a
direct 12 V feed or a switched/PWM-controlled output decides whether any software
action can start the fan at all, so this pulls the text layer of the schematic
and reports every sheet that mentions FAN.
"""

import re
from pathlib import Path

from pypdf import PdfReader

HERE = Path(__file__).resolve().parents[1]
SCHEMATIC = Path(r"D:\xilinx\xilinx\5-硬件资料\评估底板原理图\TLZ7xH-EVM评估底板原理图\TLZ7xH-EVM-B2原理图.pdf")
OUT = HERE / "tmp" / "new-board-xilinx-review" / "schematic-text"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    reader = PdfReader(str(SCHEMATIC))
    print(f"pages: {len(reader.pages)}")

    hits = []
    for number, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception as exc:                                # noqa: BLE001
            text = f"<<failed: {exc}>>"
        (OUT / f"page{number:02d}.txt").write_text(text, encoding="utf-8")
        if re.search(r"(?i)fan", text):
            hits.append((number, text))

    print(f"sheets mentioning FAN: {[n for n, _ in hits]}\n")
    for number, text in hits:
        print(f"===== page {number} =====")
        for line in text.split("\n"):
            if re.search(r"(?i)fan|12v|1n4148|pmos|nmos|mosfet|三极管|s8050|2n7002", line):
                stripped = line.strip()
                if stripped:
                    print(f"  {stripped}")


if __name__ == "__main__":
    main()
