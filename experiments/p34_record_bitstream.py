"""Record that the merged bitstream was generated, and correct the licence claim."""

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

    section = data["p34_xc7z100_license"]
    section["merged_design_status"]["bitstream_generated"] = True
    section["merged_design_status"]["bitstream"] = {
        "path": "E:/FPGA_Tools/Work/p34-bitstream-20261020/rf_display_top.bit",
        "bytes": 5037020,
        "sha256": "688475a33a284bb18ea9bcb32d19e694829e773a363e9db03bed42726b83ab67",
        "compressed": True,
        "compression_saved_bits": 99035584,
        "uncompressed_approx_bytes": 17400000,
        "drc": {"errors": 0, "warnings": 24, "advisories": 58},
        "drc_warning_kinds": {"REQP-1839 RAMB36 async control": 20,
                              "DPIP-1 DSP input pipelining": 2,
                              "RTSTAT-10 no routable loads": 1,
                              "CHECK-3 rule limit": 1},
        "elapsed_seconds": 48,
        "peak_memory_mb": 2967,
        "deployable_today": False,
        "not_deployable_because": [
            "58 CDC advisories not yet reviewed and closed",
            "this checkpoint predates the TTC0 channel 2 backlight fix",
            "WHS margin is only 13 ps",
        ],
    }
    section["record"] = "docs/experiments/P34-bitstream-generated.md"
    data["p34_xc7z100_license"] = section

    data["vision_capability_correction"] = {
        "claim_that_was_wrong": ("RF and display could not work simultaneously because the XC7Z100 rebuild "
                                 "was blocked by tool support and licensing"),
        "reality": ("the licence is valid until 2026-12-17 and the part enumerates; synthesis and "
                    "write_bitstream both succeed once XILINXD_LICENSE_FILE is set"),
        "what_actually_blocks_deployment": [
            "58 open CDC advisories",
            "the backlight TTC0 channel fix is not in the routed checkpoint",
            "WHS margin 13 ps",
        ],
        "conclusion": ("this is an engineering wrap-up, not an external dependency. The earlier "
                       "'cannot do it' judgement should not be used for planning any more."),
    }

    STATUS.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("status updated")
    print(f"  bitstream: {section['merged_design_status']['bitstream']['bytes']:,} B")
    print(f"  drc      : {section['merged_design_status']['bitstream']['drc']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
