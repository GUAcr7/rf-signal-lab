"""Record the S99board deployment attempt and what the retry path did (and did not) prove."""

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
    section = data["ad9361_probe_retry"]

    section["deployed"] = True
    section["deployed_note"] = (
        "deployed to /etc/rcS.d/S99board on 2026-10-18 19:29, sha256 "
        "1f22eae506ac98643f13f231bd7f4b6586de355e5f63b7018d6640926823d5ba, mode 755, remote hash matched"
    )
    section["retry_branch_exercised"] = False
    section["retry_branch_note"] = (
        "three reboots after deployment (19:30, 19:32 and the 19:29 check) all reported "
        "'rf ready: iio:device1 present (attempt 1)'; the PRODUCT_ID 0xFF failure occurred only once "
        "in roughly four power cycles today, so the loop's retry iteration never ran. The MECHANISM is "
        "proven - a manual rmdir + mkdir + re-apply at 19:12 turned 0xFF into 'AD936x Rev 2 "
        "successfully initialized' on the same power cycle - but the AUTOMATION of it is not."
    )
    section["what_is_proven"] = {
        "script_runs": "dmesg shows '(attempt 1)' in both the overlay and rf-ready lines, so the new code path executes",
        "rebind_mechanism": "manual rmdir/mkdir/re-apply rescues the probe on the same power cycle",
    }
    section["what_is_not_proven"] = {
        "retry_loop": "the attempt 2/3 branch has never executed on hardware",
        "how_to_force_it": "cannot be triggered on demand; needs either a real intermittent boot failure or a way to make the first probe fail deterministically",
    }
    data["ad9361_probe_retry"] = section

    STATUS.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("status updated")
    print(f"  deployed              : {section['deployed']}")
    print(f"  retry branch exercised: {section['retry_branch_exercised']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
