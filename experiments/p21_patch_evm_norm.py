"""Fix evm_db so decisions are taken on a power-normalised signal.

The bug this fixes: nearest-point decisions were computed on the raw signal
against a unit-average-power table. That is only valid when the signal amplitude
is already near the table amplitude. Scaled up 3.7x, an inner 16QAM point lands
closer to an outer table point than to its own, so the decisions were wrong and
the reported EVM was meaningless (-6.17 dB for a noise-free constellation).

Normalising to unit mean power before deciding makes the metric scale-free, which
is what a gain-invariant EVM was always supposed to be.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "src" / "rfsig" / "carrier_tracking.py"

OLD = '''    distances = np.abs(x[:, None] - table[None, :]) ** 2
    decisions = table[np.argmin(distances, axis=1)]'''

NEW = '''    # Normalise before deciding. Nearest-point decisions against a unit-power
    # table are only valid near unit power; a scaled-up 16QAM capture would
    # otherwise map inner points onto outer ones and report nonsense.
    scale = float(np.sqrt(np.mean(np.abs(x) ** 2)))
    if scale <= 0 or not np.isfinite(scale):
        raise ValueError("symbols have no usable power")
    x = x / scale

    distances = np.abs(x[:, None] - table[None, :]) ** 2
    decisions = table[np.argmin(distances, axis=1)]'''

OLD_NOTE = '''    The gain is fitted by least squares and is COMPLEX, so a constant phase'''

NEW_NOTE = '''    The signal is first normalised to unit mean power, so the reported figure is
    independent of the capture level.

    The gain is fitted by least squares and is COMPLEX, so a constant phase'''


def main() -> int:
    text = TARGET.read_text(encoding="utf-8")
    for old, new, label in ((OLD, NEW, "decision block"), (OLD_NOTE, NEW_NOTE, "docstring")):
        if old not in text:
            print(f"FAILED: {label} anchor not found")
            return 2
        text = text.replace(old, new, 1)
    TARGET.write_text(text, encoding="utf-8", newline="\n")
    print("patched evm_db normalisation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
