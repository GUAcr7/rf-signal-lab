"""Patch the three carrier-tracking tests whose premises were wrong.

1. Static phase offset: EVM with a complex gain fit absorbs a constant rotation,
   so it cannot detect one. Check the loop's converged phase instead.
2. BPSK in the three-modulation test used a zero offset, so there was nothing to
   correct.
3. Gain invariance now holds exactly because the EVM floor is relative.
"""

import io
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "tests" / "test_carrier_tracking.py"

OLD_STATIC = '''def test_tracking_removes_a_static_phase_offset():
    table = constellation("bpsk")
    clean = _symbols("bpsk", 512, seed=5)
    offset = np.deg2rad(37.0)
    rotated = clean * np.exp(1j * offset)

    before = evm_db(rotated, table)
    result = track_carrier(rotated, table, loop_bw=0.05)
    after = evm_db(result.corrected, table)

    assert before > -20, "a 37 degree offset should look bad before tracking"
    assert after < -60, f"tracking should remove it, got {after:.1f} dB"'''

NEW_STATIC = '''def test_tracking_converges_onto_a_static_phase_offset():
    # EVM deliberately cannot see this: its gain fit is complex, so a constant
    # rotation scores as a perfect constellation. The loop phase is the right
    # observable for a static offset.
    table = constellation("bpsk")
    clean = _symbols("bpsk", 512, seed=5)
    offset = np.deg2rad(37.0)
    rotated = clean * np.exp(1j * offset)

    assert evm_db(rotated, table) < -100, "static rotation must not show in EVM"

    result = track_carrier(rotated, table, loop_bw=0.05)
    converged = np.degrees(result.phase_rad[-1])
    assert converged == pytest.approx(37.0, abs=1.0), f"converged to {converged:.2f} deg"'''

OLD_THREE = '''def test_tracking_improves_all_three_modulations():
    offsets = {"bpsk": 0.0, "qpsk": 0.02, "qam16": 0.02}'''

NEW_THREE = '''def test_tracking_improves_all_three_modulations():
    offsets = {"bpsk": 0.02, "qpsk": 0.02, "qam16": 0.02}'''


def main() -> int:
    text = TARGET.read_text(encoding="utf-8")
    for old, new, label in (
        (OLD_STATIC, NEW_STATIC, "static-phase test"),
        (OLD_THREE, NEW_THREE, "three-modulation offsets"),
    ):
        if old not in text:
            print(f"FAILED: {label} anchor not found")
            return 2
        text = text.replace(old, new, 1)
    TARGET.write_text(text, encoding="utf-8", newline="\n")
    print("patched tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
