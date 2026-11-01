"""Record the P34 panel renderer work in the status file.

Adds its own top-level key rather than touching p32_current, which another
session maintains: a stale overwrite there would misreport the board state.
"""

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

    data["p34_panel_render"] = {
        "date": "2026-10-20",
        "record": "docs/experiments/P34-panel-ui.md",
        "purpose": "task 1 (show spectrum and constellation on the screen), previously blank",
        "implemented": {
            "renderer": "src/rfsig/panel_render.py",
            "cli": "experiments/p34_render_panel.py",
            "tests": "tests/test_panel_render.py (11 tests)",
        },
        "panel": {
            "pixels": [800, 480],
            "framebuffer_bytes": 1536000,
            "pixel_format": "bgra32",
            "gzip_bytes": {"bpsk": 22262, "qpsk": 21725, "qam16": 22423},
            "test_pattern_gzip_bytes": 7119,
        },
        "results": {
            "bpsk": {"evm_db": -37.18, "quadrature_suppression_db": 45.27, "amplitude_cv": 0.0127},
            "qpsk": {"evm_db": -37.07, "quadrature_suppression_db": -0.02, "amplitude_cv": 0.0083},
            "qam16": {"evm_db": -37.04, "quadrature_suppression_db": -0.12, "amplitude_cv": 0.3447},
        },
        "evm_matches_hw016": True,
        "self_inflicted_errors_fixed": [
            ("16QAM was drawn as rings because the CLI used the M-th power alignment, which is "
             "only valid for constant modulus. Fixed by tracking the carrier and searching the "
             "rotation; EVM moved from -14.96 to -37.04 dB."),
            ("the spectrum spanned the full 30.72 MHz and compressed the 240 kHz signal to a spike; "
             "it is now zoomed to +/-2 MHz around the CARRIER, not around the PSD peak, because a "
             "spurious line made the axis asymmetrical."),
        ],
        "not_verified": [
            "never displayed on the panel - would need display mode and interrupt RF work",
            "bgra32 is inferred from xilinx-drm; the channel order must be confirmed with the test pattern",
            "no live refresh; that needs the merged bitstream so RF and display can coexist",
            "no touch interaction",
        ],
        "evidence": ["results/p34-panel-bpsk-v4/", "results/p34-panel-qpsk-v4/",
                     "results/p34-panel-qam16-v4/", "results/p34-panel-testpattern/"],
    }

    data["python_tests"] = 885
    data["python_tests_note"] = "885 after adding 11 panel-render tests."

    STATUS.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("status updated")
    print("  p34_panel_render added; p32_current untouched")
    print(f"  gzip sizes: {data['p34_panel_render']['panel']['gzip_bytes']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
