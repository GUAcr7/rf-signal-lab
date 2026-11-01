"""Independent cross-check of rrc_occupied_bandwidth_hz.

Numerically integrate the analytic raised-cosine PSD (different algorithm from the
closed form in src/rfsig/bandwidth.py) and compare the 99% containment widths.
Run: python experiments/p13_rrc_obw_crosscheck.py
"""

import numpy as np

from rfsig.bandwidth import rrc_occupied_bandwidth_hz

RS = 240_000.0
BETA = 0.35


def numeric_obw(fraction, beta=BETA, rs=RS, n=4_000_001):
    """99% two-sided containment width by direct integration of the RC spectrum.

    Subtlety: the two-sided fraction inside |f| <= x equals the one-sided
    fraction E(x)/E(half), because E(half) is exactly half of the two-sided
    total. So the target on the one-sided CDF is ``fraction`` itself, NOT
    ``fraction/2``. Dividing by two here is the natural mistake and shifts the
    answer by a factor of about 2.4 at beta=0.35.
    """
    a = (1 - beta) * rs / 2
    roll = beta * rs
    half = (1 + beta) * rs / 2
    f = np.linspace(0.0, half, n)
    p = np.where(f <= a, 1.0,
                 np.where(f <= half, 0.5 * (1 + np.cos(np.pi * (f - a) / roll)), 0.0))
    cdf = np.cumsum(p) * (half / (n - 1))
    target = fraction * cdf[-1]
    return float(2 * f[int(np.searchsorted(cdf, target))])


def main():
    print(f"{'fraction':>9s} {'closed form':>12s} {'numeric':>12s} {'diff':>9s}")
    worst = 0.0
    for frac in (0.5, 0.65, 0.8, 0.9, 0.95, 0.99, 0.999):
        closed = rrc_occupied_bandwidth_hz(frac, RS, BETA)
        numeric = numeric_obw(frac)
        worst = max(worst, abs(closed - numeric))
        print(f"{frac:9.3f} {closed:12.1f} {numeric:12.1f} {closed - numeric:+9.1f}")

    print("\nboundary checks (hand-calculated):")
    print(f"  fraction=(1-beta)=0.65 -> expect (1-beta)*Rs = {(1 - BETA) * RS:.0f}, "
          f"got {rrc_occupied_bandwidth_hz(0.65, RS, BETA):.0f}")
    print(f"  fraction=1.0           -> expect support Rs*(1+beta) = {RS * (1 + BETA):.0f}, "
          f"got {rrc_occupied_bandwidth_hz(1.0, RS, BETA):.0f}")
    print(f"  beta=0, fraction=0.99  -> expect 0.99*Rs = {0.99 * RS:.0f}, "
          f"got {rrc_occupied_bandwidth_hz(0.99, RS, 0.0):.0f}")
    print(f"  beta=1, fraction=0.99  -> below support 2*Rs = {2 * RS:.0f}, "
          f"got {rrc_occupied_bandwidth_hz(0.99, RS, 1.0):.0f}")
    print(f"\nworst |closed - numeric| over the grid: {worst:.1f} Hz "
          f"({100 * worst / numeric_obw(0.99):.4f}% of the 99% width)")


if __name__ == "__main__":
    main()
