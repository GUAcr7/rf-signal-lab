"""Record the multi-buffer continuity result in the status file."""

import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "TX-SOURCE-STATUS.json"


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                          # noqa: BLE001
        pass

    data = json.loads(STATUS.read_text(encoding="utf-8-sig"))

    data["multibuffer_continuity"] = {
        "date": "2026-10-18",
        "record": "docs/experiments/EXP-HW-017-multibuffer-continuity.md",
        "question": "with a large DMA buffer, are consecutive buffers continuous?",
        "answer": "yes for two 65536-sample buffers",
        "control": {
            "case": "-b 4096, known to contain 12 jumps (EXP-HW-014)",
            "aligned": "16/16",
            "gaps": [0, 0, 0, 2000, 6293, 5602, 5773, 5595, 5740, 5760, 5536, 5814, 5719,
                     5653, 5597],
            "cells_with_abs_gap_gt_1": 12,
            "verdict": "reproduces EXP-HW-014 value for value, so the analysis code is trustworthy",
        },
        "measured": {
            "case": "-b 65536 -s 131072, two buffers",
            "aligned": "2/2",
            "source_starts": [8665, 74202],
            "gaps": [1],
            "cells_with_abs_gap_gt_1": 0,
            "correlation_min": 0.998409,
            "nmse_max_db": -24.96,
            "verdict": ("the second buffer starts 65537 samples later, one sample more than the "
                        "buffer size; modulo_gaps documents +/-1 as integer-delay estimation "
                        "resolution, so this is not a discontinuity"),
        },
        "implication": ("the jumps were caused by the small 4096-sample buffer forcing frequent "
                        "refills, not by multi-buffer reads as such. Long captures may be feasible "
                        "by enlarging the buffer, without rebuilding the producer/consumer path."),
        "caveats": [
            "only two buffers tested; 4, 8 and 16 buffers untested",
            "no lost-sample counter yet, so gap-free cannot be claimed in production",
        ],
        "transfer_note": ("a single 1.4 MB console read came back truncated; the capture is now "
                          "fetched in three sed line ranges and reassembled with a sha256 check "
                          "(experiments/p25_reassemble.py)"),
        "evidence": ["results/p25-continuity-check/continuity.json",
                     "results/p25-rx-2buf-raw/two.bin"],
    }

    data["pending_verification"] = [
        "continuity with 4, 8 and 16 large buffers, and under long running time",
        "a lost-sample counter or hardware sequence number before claiming gap-free capture",
        "real RF dataset with SNR labels and train/validation/test split",
        "which side compresses (TX or RX analogue chain) - needs a spectrum analyser tap",
        "measured confirmation of --full-scale 2048 with a known-amplitude signal",
        "screen UI and simultaneous display + RF on one bitstream",
        "whether a missing /etc/pointercal lets auto-calibration overwrite pointercal.xinput again",
    ]

    STATUS.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("status updated")
    print(f"  control gaps reproduced : {len(data['multibuffer_continuity']['control']['gaps'])}")
    print(f"  measured gap            : {data['multibuffer_continuity']['measured']['gaps']}")
    print(f"  pending                 : {len(data['pending_verification'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
