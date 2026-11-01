"""Record the block-wise carrier tracking results in the status file."""

import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "TX-SOURCE-STATUS.json"

REMAINING = [
    "still only 64 symbols per block",
    "no symbol synchronisation loop",
    "no EVM or symbol error rate",
    "only 8 blocks per class",
    "one 50 s transmission per class",
]


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                          # noqa: BLE001
        pass

    data = json.loads(STATUS.read_text(encoding="utf-8-sig"))
    if "capture_continuity_resolution" in data:
        raise RuntimeError("historical p21 summary is superseded by EXP-HW-014; refusing to overwrite current status")
    section = data["modulated_reception"]

    section["block_wise"] = {
        "method": ("split each 65,536-sample capture into 8 blocks of 8,192; estimate the "
                   "carrier, symbol phase and features independently per block"),
        "why": ("a single carrier estimate across 512 symbols made the constellation WORSE "
                "(+5.97 dB) than across 64 symbols (+11.26 dB): the boards use independent "
                "crystals, so the carrier drifts inside a long block"),
        "method_fixes": [
            ("replaced the 500 Hz grid search with modulation-stripped FFT plus parabolic "
             "interpolation; the moment peak is about 470 Hz wide, narrower than the grid step, "
             "so the search walked to its window edge and reported -206 kHz"),
            ("widened the per-block moment search to the full span; the narrow band excluded the "
             "real peak near 2 x 1 MHz and produced carrier estimates scattered over 33-361 kHz"),
        ],
        "features": {
            "bpsk": {"quadrature_suppression_db": [26.08, 16.14], "amplitude_cv": [0.360, 0.215]},
            "qpsk": {"quadrature_suppression_db": [0.17, 1.31], "amplitude_cv": [0.137, 0.085]},
            "qam16": {"quadrature_suppression_db": [-0.17, 0.67], "amplitude_cv": [0.393, 0.057]},
        },
        "separability": {
            "bpsk_vs_rest": ("quadrature suppression min +9.04 dB (BPSK) vs max +2.94 dB "
                             "(others): a 6.1 dB gap with no overlap"),
            "qpsk_vs_qam16": ("amplitude CV max 0.294 (QPSK) vs min 0.346 (16QAM): a 0.052 gap, "
                              "about 15 percent relative - much tighter than the BPSK line"),
        },
        "carrier_offset": ("987-994 kHz across three independent captures, i.e. +28 to +34 kHz from "
                           "the 960 kHz nominal, about 11-14 ppm at 2450 MHz; consistent enough to "
                           "treat as a measurement"),
        "evidence": [
            "results/p21-bpsk-blocks2/blocks.json",
            "results/p21-qpsk-blocks/blocks.json",
            "results/p21-qam16-blocks/blocks.json",
        ],
        "remaining": REMAINING,
    }
    section["limitations"] = REMAINING
    section["separability"] = section["block_wise"]["separability"]
    data["modulated_reception"] = section

    data["pending_verification"] = [
        ("longer blocks (256-512 symbols) WITH intra-block carrier tracking, which is the actual "
         "next step rather than either alone"),
        "EVM and symbol-error-rate metrics",
        "which side compresses (TX or RX analogue chain) - needs a spectrum analyser tap",
        "measured confirmation of --full-scale 2048 with a known-amplitude signal",
        "whether a missing /etc/pointercal lets auto-calibration overwrite pointercal.xinput again",
    ]

    STATUS.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("status updated")
    print(f"  separability bpsk : {section['separability']['bpsk_vs_rest']}")
    print(f"  pending           : {len(data['pending_verification'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
