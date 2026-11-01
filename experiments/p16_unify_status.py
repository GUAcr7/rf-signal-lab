"""Bring TX-SOURCE-STATUS.json in line with the corrected records.

The independent review found the status file still carried conclusions that had
already been retracted elsewhere:

  * a status_note saying "9 timed transmissions" while the verified count is 25
  * frequency_verified_scope asserting a +/-5 kHz (+/-2 ppm) bound, which was
    later reduced to "observed scatter, not a calibrated bound"
  * physical_dependencies claiming the new board was not connected and that the
    attenuator was "no longer blocking" (that conclusion was retracted)
  * display / autostart flags reading as verified although no transcript for
    those checks was ever archived

This script rewrites exactly those fields. It is idempotent, and it refuses to
run if the file fails to parse, so a half-written status can never be produced.
"""

import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "TX-SOURCE-STATUS.json"


def main() -> int:
    try:
        data = json.loads(STATUS.read_text(encoding="utf-8-sig"))
    except Exception as exc:                                   # noqa: BLE001
        print(f"FAILED to parse {STATUS}: {exc}")
        return 2

    # --- 1. status: the new board IS connected now -------------------------
    data["status"] = (
        "old_board_rf_transmit_verified; "
        "new_board_connected_display_and_iio_enumerated_but_evidence_pending"
    )
    data["status_note"] = (
        "旧 P201 已实际执行 25 次限时射频发送（频率/功率/占用带宽/相对功率均已验证，"
        "证据为频谱仪照片与串口 transcript）。新板 TLZ7xH-EVM 已接入并跑通显示与 AD9361 枚举，"
        "但显示/自启/触摸持久化三项的原始 transcript 尚未归档（见 EXP-HW-006 第 11 节），"
        "真实 I/Q 采集、模式往返、双板连接均未验证。"
    )
    data["status_note_supersedes"] = (
        'the previous note said "9 timed transmissions" and "second board RX not connected"; '
        "both were stale."
    )

    # --- 2. frequency: observation only -----------------------------------
    data["frequency_verified_scope"] = (
        "Observed only: three analyser OBW-centre readings were -1.829 / -4.767 / -0.262 kHz "
        "(mean -2.29 kHz, peak-to-peak 4.5 kHz). This is the scatter of the estimator on this "
        "signal, NOT a calibrated accuracy bound; the analyser frequency reference is "
        "uncalibrated and board-versus-instrument contributions cannot be separated."
    )
    data.pop("measured_tx_frequency_error_ppm", None)
    data["measured_tx_frequency_error_ppm_observed"] = -0.93
    data["measured_tx_frequency_error_ppm_scope"] = (
        "-0.93 ppm is the observed mean offset, not a ppm-level accuracy claim. "
        "See EXP-P13-OBW sections 6.4 and 10.2."
    )

    # --- 3. dependencies: drop the retracted attenuator claim --------------
    data["physical_dependencies"] = [
        "旧板必须 5V/1A USB 加强线直插电脑 USB 口，不经集线器；否则 AD9361 读回非法（EXP-HW-004）",
        "新板 TLZ7xH-EVM + FMCOMMS3 已接入；显示与 AD9361 枚举已观察，但原始证据待补（EXP-HW-006 第 11 节）",
        "双板射频连接前必须先做降幅与饱和检查，见 docs/design/rx-input-budget-20261017.md",
        "老师现用的显示系统与屏幕型号/接口（若要保留其现有方案）",
        "板卡绝对频率标定需要已知频率基准或共用参考时钟",
    ]
    data["two_board_plan"] = "docs/design/rx-input-budget-20261017.md"
    data["two_board_plan_superseded"] = (
        "docs/design/two-board-rf-link.md (kept for history; its step 2 warning about not "
        "using the 2.5 dBm absolute max is the rule that was violated)"
    )

    # --- 4. display / autostart / touch: evidence honesty -----------------
    board = data.get("new_board", {})

    display = board.get("display", {})
    display["working"] = "observed_not_archived"
    display["evidence_status"] = "observed_but_window_not_archived"
    display["evidence_note"] = (
        "The xilinx-drm fb0 registration, the 100x30 console switch and the post-reboot checks "
        "were read through p15_serial_read.py, which does not write transcripts. No archived "
        "proof exists. Capture plan: EXP-HW-006 section 11."
    )
    board["display"] = display

    autostart = board.get("boot_autostart", {})
    autostart["verified_after_reboot"] = "observed_not_archived"
    autostart["evidence_status"] = "observed_but_window_not_archived"
    board["boot_autostart"] = autostart

    touch = board.get("touch", {})
    touch["reboot_verified"] = False
    touch["evidence_status"] = "raw_events_archived; post_reboot_persistence_not_yet_verified"
    board["touch"] = touch

    data["new_board"] = board

    # --- 5. machine-checkable promise list --------------------------------
    data["pending_verification"] = [
        "display evidence transcript (EXP-HW-006 section 11 A)",
        "autostart after reboot with transcript (EXP-HW-006 section 11 A)",
        "touch persistence after reboot, props 243/244 (EXP-HW-006 section 11 B)",
        "touch raw events re-captured with transcript (EXP-HW-006 section 11 C)",
        "mode switch display -> rf -> display round trip",
        "old board five-step non-transmitting recovery",
        "new board config readback + real short I/Q + format stats + stop/restart capture",
        "two-board RF connection after amplitude reduction and saturation checks",
    ]

    STATUS.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("status json unified")
    print(f"  status                 : {data['status']}")
    print(f"  RF_transmit_count      : {data.get('RF_transmit_count')}")
    print(f"  display working        : {board['display']['working']}")
    print(f"  autostart after reboot : {board['boot_autostart']['verified_after_reboot']}")
    print(f"  touch reboot_verified  : {board['touch']['reboot_verified']}")
    print(f"  pending items          : {len(data['pending_verification'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
