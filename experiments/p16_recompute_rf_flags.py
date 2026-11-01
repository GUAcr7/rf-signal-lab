"""Recompute RF-operation flags from archived serial transcripts.

Why: ``experiments/p06_arm_serial_run.ps1`` initialised ``rf_operations`` to a
hardcoded ``$false`` and never updated it. Every transmitting run therefore
archived ``rf_operations=false`` even though the transcript shows samples being
pushed into the TX DMA buffer, which makes the archive read as if no RF had ever
been emitted.

The original ``report.json`` files are deliberately NOT rewritten: the project
rule is to append corrections, not to alter history. This script instead writes
a separate index that recomputes the flags from the transcripts, so the original
archive stays byte-identical while a correct summary exists beside it.

Detection is evidence-based, from the serial transcript only:
  CYCLIC_PUSH_SUBMITTED    samples reached the TX DMA buffer
  TX_SOFTWARE_DEADLINE_END the timed transmit finished under its own deadline
  rf_settings_written=true the host wrote RF/PHY attributes (should be false
                           for every run in this project)
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"

PUSH = "CYCLIC_PUSH_SUBMITTED"
DEADLINE = "TX_SOFTWARE_DEADLINE_END"
RF_WRITE = re.compile(r"rf_settings_written=(true|false)")
CHECK_PASS = "INPUT_CHECK_PASS"
CLEANUP = "TX_CLEANUP"


def classify(transcript: str) -> dict:
    pushed = PUSH in transcript
    ended = DEADLINE in transcript
    writes = RF_WRITE.findall(transcript)
    wrote_rf = "true" in writes
    return {
        "rf_operations": pushed,
        "rf_transmitted": bool(pushed and ended),
        "rf_operations_basis": (
            "transcript contains CYCLIC_PUSH_SUBMITTED"
            if pushed
            else "transcript contains no CYCLIC_PUSH_SUBMITTED (read-only run)"
        ),
        "rf_settings_written_by_host": wrote_rf,
        "input_check_passed": CHECK_PASS in transcript,
        "cleanup_recorded": CLEANUP in transcript,
        "deadline_ended": ended,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        help="index path (default results/rf-flags-recomputed-<utc>.json)")
    args = parser.parse_args()

    rows = []
    unreadable = []
    for report_path in sorted(RESULTS.glob("*/report.json")):
        directory = report_path.parent
        transcript_path = directory / "serial-transcript.txt"
        if not transcript_path.is_file():
            continue
        transcript = transcript_path.read_text(encoding="utf-8", errors="replace")
        # PowerShell's `Set-Content -Encoding utf8` writes a BOM, which makes
        # plain json.loads throw. Reading as utf-8-sig strips it. The first
        # version of this script swallowed that exception and silently treated
        # every archived report as absent, which produced a wrong "0 wrong
        # flags" summary - so parse failures are now counted, not hidden.
        try:
            original = json.loads(report_path.read_text(encoding="utf-8-sig"))
        except Exception as exc:                               # noqa: BLE001
            unreadable.append({"evidence_dir": directory.name, "error": str(exc)})
            original = {}
        computed = classify(transcript)
        archived = original.get("rf_operations")
        rows.append({
            "evidence_dir": directory.name,
            "archived_rf_operations": archived,
            "archived_rf_transmitted": original.get("rf_transmitted"),
            "recomputed": computed,
            "archived_was_wrong": (
                archived is not None and bool(archived) != computed["rf_operations"]
            ),
            "report_sha256_note": "original report.json left unmodified",
        })

    wrong = [r for r in rows if r["archived_was_wrong"]]
    transmitted = [r for r in rows if r["recomputed"]["rf_transmitted"]]
    wrote_rf = [r for r in rows if r["recomputed"]["rf_settings_written_by_host"]]
    missing_flag = [r for r in rows if r["archived_rf_operations"] is None]

    out = args.output or RESULTS / datetime.now(timezone.utc).strftime(
        "rf-flags-recomputed-%Y%m%dT%H%M%SZ.json")
    payload = {
        "schema": "rfsig.rf_flags_recomputed.v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "method": "flags recomputed from serial-transcript.txt; originals untouched",
        "summary": {
            "directories_scanned": len(rows),
            "reports_unreadable": len(unreadable),
            "archived_flag_present_but_wrong": len(wrong),
            "archived_flag_absent": len(missing_flag),
            "runs_that_actually_pushed_samples": len(transmitted),
            "runs_that_wrote_rf_settings": len(wrote_rf),
        },
        "unreadable": unreadable,
        "rows": rows,
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"scanned {len(rows)} evidence directories")
    print(f"reports unreadable            : {len(unreadable)}")
    print(f"archived flag present but wrong: {len(wrong)}")
    print(f"archived flag absent          : {len(missing_flag)}")
    print(f"actually pushed samples       : {len(transmitted)}")
    print(f"wrote RF settings             : {len(wrote_rf)}  (expected 0)")
    print(f"index: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
