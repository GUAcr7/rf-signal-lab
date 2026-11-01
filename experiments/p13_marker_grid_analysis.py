"""Test whether the claimed +2.5 kHz LO offset was real or grid quantisation.

The 2026-10-16 tone photos used span 10 MHz with 801 trace points, so the marker
can only land on a 12.5 kHz grid. This script asks: with LO offset exactly zero,
what would the analyser have displayed for the +960 kHz and -960 kHz tones?

If zero offset reproduces BOTH recorded readings and the apparent 5 kHz widening
of the peak separation, then the earlier "+2.5 kHz LO offset" conclusion was an
artefact of that grid, not a property of the board.
"""

SPAN_HZ = 10.0e6
POINTS = 801
CENTER_HZ = 2_450_000_000.0
STEP_HZ = SPAN_HZ / (POINTS - 1)

MEASURED = {"tone-positive": 2_450_962_500.0, "tone-negative": 2_449_037_500.0}
TRUE_OFFSET = {"tone-positive": 960_000.0, "tone-negative": -960_000.0}


def main():
    print(f"marker grid: span {SPAN_HZ/1e6:g} MHz, {POINTS} points -> step = {STEP_HZ:.1f} Hz\n")
    all_match = True
    for name, offset in TRUE_OFFSET.items():
        true_hz = CENTER_HZ + offset
        steps = offset / STEP_HZ
        nearest = round(steps)
        predicted = CENTER_HZ + nearest * STEP_HZ
        match = abs(predicted - MEASURED[name]) < 1e-6
        all_match &= match
        print(f"{name}")
        print(f"  true frequency            : {true_hz:,.0f} Hz")
        print(f"  offset in grid steps      : {steps:+.4f}")
        print(f"  nearest whole grid point  : {nearest:+d}")
        print(f"  predicted display @ 0 LO  : {predicted:,.0f} Hz")
        print(f"  actually recorded         : {MEASURED[name]:,.0f} Hz")
        print(f"  match                     : {'YES' if match else 'NO'}")
        print(f"  apparent error vs truth   : {MEASURED[name] - true_hz:+,.0f} Hz\n")

    separation = MEASURED["tone-positive"] - MEASURED["tone-negative"]
    nearest_pair = round(1_920_000.0 / STEP_HZ)
    print("peak separation")
    print(f"  true                      : 1,920,000 Hz = {1_920_000.0/STEP_HZ:.4f} steps")
    print(f"  nearest whole-step pair   : {nearest_pair} steps = {nearest_pair*STEP_HZ:,.0f} Hz")
    print(f"  actually recorded         : {separation:,.0f} Hz")
    print(f"  match                     : {'YES' if abs(nearest_pair*STEP_HZ - separation) < 1e-6 else 'NO'}\n")

    print("=" * 68)
    if all_match:
        print("RESULT: zero LO offset reproduces both readings and the 5 kHz gap.")
        print("        The '+2.5 kHz LO offset' claim is NOT supported by these")
        print("        photos; the numbers are explained by 12.5 kHz quantisation.")
    else:
        print("RESULT: zero LO offset does NOT reproduce the readings.")


if __name__ == "__main__":
    main()
