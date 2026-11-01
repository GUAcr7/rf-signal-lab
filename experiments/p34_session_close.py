"""Close out the 2026-10-20 session: record totals and the remaining-task list."""

import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "TX-SOURCE-STATUS.json"

REMAINING = {
    "immediate": [
        {
            "task": "rebuild the combined device tree by concatenating the two factory DTS files",
            "why": "the bitstream works with either vendor overlay; only our hand-built overlay hangs the board",
            "effort": "1-2 hours, route already written down",
            "blocks": "everything about RF plus display at the same time",
        },
        {
            "task": "verify RF and display come up in a single boot",
            "why": "that is the actual goal of the merged bitstream",
            "effort": "a few boots",
            "blocks": "live spectrum on the board LCD",
        },
    ],
    "then": [
        {
            "task": "add live libiio capture to the on-board panel program",
            "why": "arm_panel now reads a file; live RF needs the capture block dropped into load_iq()",
            "effort": "about 1 day",
            "note": "capture pattern already proven by arm_rx_diagnostic.c (dlopen libiio, 0.20 compatible)",
        },
        {
            "task": "refresh loop and boot integration",
            "why": "one frame per run today; needs a continuous loop and start-at-boot",
            "effort": "half a day",
            "note": "2.34 ms per frame already measured, so the budget is not the problem",
        },
        {
            "task": "constellation and waterfall on the board",
            "why": "the panel currently draws spectrum only",
            "effort": "about 1 day",
            "note": "host-side layout and demodulation already validated",
        },
    ],
    "still_open_from_before": [
        {
            "task": "58 CDC advisories review",
            "why": "not the cause of tonight's hang, but still unreviewed and the design is unchanged",
            "owner": "the other session (P33 documents)",
        },
        {
            "task": "WHS margin of 13 ps and no custom OCV derate",
            "why": "met, but thin; a derated run would say whether it is real",
            "effort": "half a day",
        },
        {
            "task": "continuous IQ without dropped samples",
            "why": "every tested configuration still has lossless_proven=false",
            "effort": "unknown, needs capture-path work",
        },
        {
            "task": "real AI dataset with SNR labels and a train/validation/test split",
            "why": "modulation recognition is still a baseline on synthetic or recorded segments",
            "effort": "several days",
        },
        {
            "task": "touch interaction on the panel",
            "why": "no code reads the touchscreen today",
            "effort": "half a day",
        },
        {
            "task": "restore and re-verify the old board RAM TX package",
            "why": "not restored this session; required before any transmission from the old board",
            "effort": "under an hour",
        },
    ],
    "not_blocking_but_worth_closing": [
        "abort and independent-reset tests for the DMA paths",
        "external IO timing verification",
        "simulation before the next bitstream deployment (tonight proved static checks are not enough)",
    ],
}


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                          # noqa: BLE001
        pass

    data = json.loads(STATUS.read_text(encoding="utf-8-sig"))

    data["p34_session_close"] = {
        "date": "2026-10-20",
        "worklog": "docs/handoff/WORKLOG-20261020-P34.md",
        "start_here_updated": True,
        "board_state_at_stop": {
            "responsive": False,
            "detail": ("after the last serial batch the board stopped answering: CH340 present, port opens, "
                       "zero bytes returned. Power cycle required before the next session."),
            "unconfirmed": ("the vendor file restore (display.bin / system_wrapper.bin / ad9361.bin from .vb, "
                            "board-mode back to display) was in flight and did not finish visibly"),
            "how_to_check": "sha256sum display.bin system_wrapper.bin ad9361.bin; cat /etc/board-mode",
            "artifacts_kept_on_board": ["/lib/firmware/p32.raw", "/lib/firmware/p32-test.dtbo"],
        },
        "headline": ("the merged bitstream was proven good on hardware: AD9361 initialises and four IIO "
                     "devices appear under the vendor RF tree, DRM and fb0 come up under the vendor display "
                     "tree. Only our hand-built combined overlay hangs the board."),
        "remaining_work": REMAINING,
        "remaining_count": {
            "immediate": len(REMAINING["immediate"]),
            "then": len(REMAINING["then"]),
            "still_open_from_before": len(REMAINING["still_open_from_before"]),
            "total_items": (len(REMAINING["immediate"]) + len(REMAINING["then"])
                            + len(REMAINING["still_open_from_before"])),
        },
    }

    STATUS.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    counts = data["p34_session_close"]["remaining_count"]
    print("status: p34_session_close recorded")
    print(f"  remaining: {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
