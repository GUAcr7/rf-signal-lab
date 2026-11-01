"""Record the 2026-10-18 cold-start reproduction results in the status file."""

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

    data["cold_start_reproduction"] = {
        "date": "2026-10-18",
        "record": "docs/experiments/EXP-HW-016-cold-start-reproduction.md",
        "verified": True,
        "results": {
            "bpsk": {"carrier_hz": 993213.6, "timing": 49, "evm_db": -37.18,
                     "quadrature_suppression_db": 45.27, "amplitude_cv": 0.0127},
            "qpsk": {"carrier_hz": 993455.6, "timing": 7, "evm_db": -37.07,
                     "quadrature_suppression_db": -0.02, "amplitude_cv": 0.0083},
            "qam16": {"carrier_hz": 993654.7, "timing": 36, "evm_db": -37.04,
                      "quadrature_suppression_db": 0.05, "amplitude_cv": 0.3447},
        },
        "capture_sha256": {
            "bpsk": "0d06610cd1a50d5d11c846edbb649e4465d21ae85bc54102a47ffe682c853f3b",
            "qpsk": "d24026928e338b3618d9170e055a8d8394ddda4c50c4c50fdf0ac81cc07ae1a2",
            "qam16": "d8e4f729b262f8dae52f644420e2260da00f86f9b121f6cc09f0cc54fbbb73b6",
        },
        "separability": {"bpsk_quad_gap_db": 45.2, "qpsk_vs_qam16_cv_ratio": 41.5},
        "note": ("all three within 0.14 dB of each other; the 16QAM figure improved from -23.80 to "
                 "-37.04 because the carrier is now tracked by a PLL before rotation alignment"),
    }

    data["ad9361_probe_retry"] = {
        "problem": ("at boot the AD9361 probe returned PRODUCT_ID 0xFF and the rf-mode check aborted the "
                    "bring-up, leaving the board with no RF"),
        "evidence": ("first probe at spi32765 returned 0xFF; after re-applying the overlay a probe at "
                     "spi32764 reported AD936x Rev 2 successfully initialized and the ADC/DDS cores "
                     "probed - same power cycle"),
        "fix": ("S99board now waits up to 6 s for iio:device1 after applying the overlay and, if missing, "
                "rebinds the overlay up to 3 attempts before failing. File grew 5040 -> 6193 bytes, "
                "17 return-code checks kept, dash -n clean."),
        "deployed": False,
        "deployed_note": "not yet copied to the board; the retry path has never executed on hardware",
        "evidence_policy": "results/p24-overlay-rebind3-20261018/",
    }

    data["carrier_must_be_reestimated"] = {
        "observation": ("today 993,213-993,655 Hz; yesterday 994,448-994,639 Hz; about 1.2 kHz between "
                        "power cycles"),
        "implies": ("roughly 40 ppm variation across power cycles; never reuse a carrier estimate from a "
                    "previous session"),
    }

    data["pending_verification"] = [
        "deploy the new S99board retry logic and prove the retry path on a real reboot",
        "long-duration gap-free streaming (still only a single-buffer 2.133 ms snapshot)",
        "real RF dataset with SNR labels and train/validation/test split",
        "which side compresses (TX or RX analogue chain) - needs a spectrum analyser tap",
        "measured confirmation of --full-scale 2048 with a known-amplitude signal",
        "screen UI and simultaneous display + RF on one bitstream",
        "whether a missing /etc/pointercal lets auto-calibration overwrite pointercal.xinput again",
    ]

    STATUS.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("status updated")
    print(f"  pending = {len(data['pending_verification'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
