"""Correct the desktop environment name in the records: LXDE -> XFCE.

Evidence: /var/log/Xsession.log on the board shows xfce4-session, xfsettingsd,
x-session-manager and a path under /home/root/.cache/sessions/xfce4-session-*.
Several documents claimed LXDE, which was wrong.

Rewrites only the substring "LXDE" and reports the count per file, so the change
is auditable rather than a blind global replace.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TARGETS = [
    "docs/experiments/EXP-HW-006-TLZ7xH-display-and-fan.md",
    "docs/experiments/EXP-REVIEW-HANDOFF-20261017.md",
    "docs/design/NEW-BOARD-RESUME.md",
    "START-HERE.md",
]


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                          # noqa: BLE001
        pass

    total = 0
    for relative in TARGETS:
        path = ROOT / relative
        if not path.is_file():
            print(f"  MISSING {relative}")
            continue
        text = path.read_text(encoding="utf-8")
        before = text.count("LXDE")
        if before == 0:
            print(f"  {relative:56s} no LXDE occurrences")
            continue
        text = text.replace("LXDE", "XFCE")
        path.write_text(text, encoding="utf-8")
        after = text.count("LXDE")
        total += before
        print(f"  {relative:56s} {before} -> {after}")

    print(f"\nreplaced {total} occurrence(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
