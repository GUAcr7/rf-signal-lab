"""Record the 2026-10-17 evening board verification results in the status file.

Closed this round, all with archived transcripts:
  * display autostart (state=operating, /dev/fb0, gpio914=out, dmesg fb0+100x30)
  * touch persistence across reboot (243 = 0,1 and 244 = 0,4095,0,4095, X alive,
    Divide-by-Zero count 70 -> 0)

Also records the four X-session gotchas that cost most of the evening, so they
are not rediscovered later.
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
    board = data["new_board"]

    board["display"] = {
        "working": True,
        "evidence_status": "archived",
        "evidence": "results/p16e-autostart-20261017/transcript.json",
        "readings": {
            "fpga_state": "operating",
            "dev_fb0": "present",
            "gpio914_direction": "out",
            "dmesg": ("Console: switching to colour frame buffer device 100x30; "
                      "xilinx-drm fb0: frame buffer device"),
        },
    }
    board["desktop"] = "XFCE (corrected: earlier records said LXDE, which was wrong)"

    board["touch"] = {
        "working": True,
        "driver": "ads7846 / XPT2046",
        "root_cause_of_initial_failure": (
            "evdev calibration was degenerate (2915,2915,2759,2662), loaded from "
            "/etc/pointercal.xinput"
        ),
        "reboot_verified": True,
        "evidence": "results/p16e-touch-final-20261017/transcript.json",
        "readings_after_reboot": {
            "243_inversion": "0, 1",
            "244_calibration": "0, 4095, 0, 4095",
            "divide_by_zero_in_Xsession_log": 0,
            "Xorg_alive": True,
        },
        "persisted_by": [
            "/etc/pointercal.xinput (primary, loaded by X every session)",
            "/etc/X11/Xsession.d/99touch (fallback, runs last in ls -X order)",
        ],
        "manual_tap_test": ("NOT DONE - properties and warning count verified, "
                            "an actual tap was not exercised"),
    }

    board["boot_autostart"] = {
        "script": "/etc/rcS.d/S99board",
        "deployed_version": "fixed-display-only (sha256 c9a5b2649d6f)",
        "mode_driven_version": "board/boot/S99board sha256 2bfc9e5f8cb7 - NOT DEPLOYED",
        "verified_after_reboot": True,
        "evidence": "results/p16e-autostart-20261017/transcript.json",
        "note": "display and fan both came up unattended; fan is PS MIO8, bitstream independent",
    }

    data["new_board"] = board

    data["x_session_findings"] = {
        "session_client": "xinit /etc/X11/Xsession -- Xorg (from /etc/init.d/xserver-nodm)",
        "hooks_are_sourced": ("/etc/X11/Xsession sources every executable file in "
                             "Xsession.d; an `exit` there kills the whole session"),
        "xinit_d_is_inert": ("/etc/X11/Xinit.d is only used by /etc/X11/Xinit, which this "
                            "boot path does not invoke"),
        "exec_bit_required": ("Xsession only sources files that are executable; base64 "
                             "uploads land as 644 and are silently skipped"),
        "calibration_file": ("/etc/pointercal.xinput is loaded by X every session; it held "
                            "degenerate values written by the vendor auto-calibration scripts"),
        "record": "docs/experiments/EXP-HW-007-touch-persistence.md",
    }

    data["pending_verification"] = [
        "human tap test on the touchscreen (properties are right, a real tap was not exercised)",
        "deploy the mode-driven S99board and verify display -> rf -> display round trip",
        "old board five-step non-transmitting recovery",
        "new board config readback + real short I/Q + format stats + stop/restart capture",
        "two-board RF connection after amplitude reduction and saturation checks",
        "whether a missing /etc/pointercal lets auto-calibration overwrite pointercal.xinput again",
    ]

    STATUS.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("status updated")
    print(f"  display working      : {board['display']['working']}  evidence={board['display']['evidence_status']}")
    print(f"  touch reboot_verified: {board['touch']['reboot_verified']}")
    print(f"  autostart            : {board['boot_autostart']['verified_after_reboot']}")
    print(f"  pending items        : {len(data['pending_verification'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
