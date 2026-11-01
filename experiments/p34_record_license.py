"""Record the XC7Z100 license blocker: it was an environment problem, not an expiry.

EXP-HW-019 concluded that rebuilding for XC7Z100 was blocked by "tool support and
licensing". A routed merged design for 7z100-ffg900 exists from 2026-10-19, which
contradicts that. Re-probing on 2026-10-20 found the part is enumerable and
synthesis succeeds once the license is pointed at. The installed copy under
AppData was gone; the original download was still on E:.

Also worth recording: the routed DCP closes timing, so the remaining gap is
process (CDC review, PWM2 merge) rather than capability.
"""

import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "TX-SOURCE-STATUS.json"

SECTION = {
    "date": "2026-10-20",
    "question": "can this machine synthesise for xc7z100ffg900-2?",
    "answer": "yes, once XILINXD_LICENSE_FILE points at the license file",
    "previous_conclusion": {
        "where": "EXP-HW-019 section 4 and START-HERE",
        "claim": "XC7Z100 rebuild blocked by missing tool support and licensing",
        "status": "superseded",
        "why_it_looked_blocked": [
            "the installed license copy at %APPDATA%\\XilinxLicense\\Xilinx.lic is gone; only the original download survived",
            "LM_LICENSE_FILE points at D:\\modelsim\\LICENSE.TXT, which does not carry the Xilinx features",
        ],
    },
    "probe_result": {
        "tool": "Vivado 2021.1",
        "part_enumerable": "P27_PART_COUNT 1, twelve xc7z100 variants listed",
        "with_license": "INFO [Common 17-349] Got license for feature 'Synthesis' and/or device 'xc7z100' and P27_SYNTHESIS_CAPABILITY_PASS",
        "without_license": "ERROR [Common 17-345] a valid license was not found; exit 4",
    },
    "license": {
        "path": "E:/FPGA_Tools/Downloads/Xilinx.lic",
        "bytes": 3012,
        "features": ["Vivado_Enterprise_Package", "Vivado_ML_Enterprise_Edition",
                     "Vivado_Simulation", "ISE_Embedded_Edition"],
        "start": "17-Oct-2026",
        "expires": "17-dec-2026 (60-day evaluation)",
        "hostid": "40c2ba523054 (node locked)",
    },
    "fix_applied": "user environment variable XILINXD_LICENSE_FILE set to E:/FPGA_Tools/Downloads/Xilinx.lic; LM_LICENSE_FILE left untouched",
    "merged_design_status": {
        "checkpoint": "E:/p30c-1019-174235/merged-route.dcp",
        "bytes": 28854850,
        "device": "7z100-ffg900",
        "timing": {"WNS_ns": 0.449, "WHS_ns": 0.013, "failing_endpoints": 0,
                   "report": "All user specified timing constraints are met."},
        "utilization_percent": {"LUT": 7.87, "FF": 6.93, "BRAM": 1.66, "DSP": 3.42},
        "bitstream_generated": False,
        "caveats": [
            "58 CDC critical items still open",
            "the routed checkpoint predates the TTC0 channel 2 backlight fix, which lives in the unsynthesised p32-pwm2 project",
            "WHS margin of 13 ps is very thin and deserves a hold-path look before deployment",
        ],
    },
    "evidence": [
        "E:/FPGA_Tools/Work/p34-part-probe-20261020/probe4.log",
        "E:/p30c-1019-174235/merged-route-timing.rpt",
        "E:/p30c-1019-174235/merged-route-utilization.rpt",
    ],
}


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                          # noqa: BLE001
        pass

    data = json.loads(STATUS.read_text(encoding="utf-8-sig"))
    data["p34_xc7z100_license"] = SECTION
    STATUS.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("status updated: p34_xc7z100_license")
    print(f"  answer: {SECTION['answer']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
