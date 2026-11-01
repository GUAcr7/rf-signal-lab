"""Patch evm_db: relative floor and document that a constant phase is invisible.

Kept as a script rather than a shell one-liner because the docstring contains an
apostrophe and quotes, which PowerShell mangles.
"""

import io
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "src" / "rfsig" / "carrier_tracking.py"

OLD_BODY = '''    error_power = float(np.mean(np.abs(x - reference) ** 2))
    signal_power = float(np.mean(np.abs(reference) ** 2))
    if signal_power <= 0:
        raise ValueError("reference has no power")
    return float(10 * np.log10(max(error_power, 1e-30) / signal_power))'''

NEW_BODY = '''    error_power = float(np.mean(np.abs(x - reference) ** 2))
    signal_power = float(np.mean(np.abs(reference) ** 2))
    if signal_power <= 0:
        raise ValueError("reference has no power")
    # The floor is relative, not absolute. An absolute floor makes a perfect
    # constellation report -300 dB at one scale and -309 dB at another, which
    # breaks gain invariance in exactly the case the metric is meant to have it.
    ratio = max(error_power / signal_power, RELATIVE_FLOOR)
    return float(10 * np.log10(ratio))'''

OLD_DOC = '''    The gain is fitted by least squares so this measures phase and noise error
    rather than a level mismatch, which is what a carrier-tracking comparison
    needs to isolate.'''

NEW_DOC = '''    The gain is fitted by least squares and is COMPLEX, so a constant phase
    rotation counts as gain and is invisible here: a constellation rotated by a
    fixed angle still scores as a perfect constellation. That is the right
    semantics for "how close to an ideal shape", but it means EVM cannot be used
    to prove that a static carrier offset was corrected; check the converged
    loop phase for that. Only time-varying phase (a frequency offset) shows up
    in this metric.'''

ANCHOR = "from numpy.typing import ArrayLike, NDArray"
FLOOR_BLOCK = (
    "from numpy.typing import ArrayLike, NDArray\n\n"
    "# Floor for the EVM ratio, far below any physically meaningful error.\n"
    "RELATIVE_FLOOR = 1e-15\n"
)


def main() -> int:
    text = TARGET.read_text(encoding="utf-8")
    for old, new, label in (
        (OLD_BODY, NEW_BODY, "body"),
        (OLD_DOC, NEW_DOC, "docstring"),
        (ANCHOR, FLOOR_BLOCK, "floor constant"),
    ):
        if old not in text:
            print(f"FAILED: {label} anchor not found")
            return 2
        text = text.replace(old, new, 1)
    TARGET.write_text(text, encoding="utf-8", newline="\n")
    print("patched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
