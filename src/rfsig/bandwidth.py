"""Equal-tail bandwidth of an explicit PSD region; not a signal detector."""

from dataclasses import dataclass
from numbers import Real

import numpy as np
from numpy.typing import ArrayLike


def _scalar(value, name):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real) or not np.isfinite(value):
        raise ValueError(f"{name} must be a finite real scalar")
    return float(value)


@dataclass(frozen=True)
class OccupiedBandwidth:
    status: str
    lower_hz: float | None
    upper_hz: float | None
    bandwidth_hz: float | None
    center_baseband_hz: float | None
    center_rf_hz: float | None
    observed_region_power: float
    effective_region_power: float
    occupied_fraction: float
    analysis_band_hz: tuple[float, float]
    bin_width_hz: float
    noise_floor_psd: float
    min_effective_power: float


def occupied_bandwidth(
    frequency_hz: ArrayLike,
    psd: ArrayLike,
    analysis_band_hz: tuple[float, float],
    occupied_fraction: float = 0.99,
    noise_floor_psd: float = 0.0,
    min_effective_power: float = 0.0,
    rf_lo_hz: float | None = None,
) -> OccupiedBandwidth:
    """Integrate a uniform grid using constant density inside each bin cell.

    Equal lower/upper tails define interpolated edges, not measured sub-bin
    accuracy. Fixed noise subtraction is clipped at zero. Positive effective
    power describes a spectral distribution and does not prove a target exists.
    Caller must keep the ROI inside a non-wrapping observed frequency interval.
    """
    f, density = np.asarray(frequency_hz), np.asarray(psd)
    if f.ndim != 1 or f.size < 2 or f.dtype.kind not in "iuf":
        raise ValueError("frequency_hz must be a numeric 1D array of at least two bins")
    if density.shape != f.shape or density.dtype.kind not in "iuf":
        raise ValueError("PSD must be a real numeric vector matching the frequency axis")
    f, density = f.astype(np.float64), density.astype(np.float64)
    if not np.isfinite(f).all() or not np.isfinite(density).all() or np.any(density < 0):
        raise ValueError("Frequencies and nonnegative PSD must be finite")
    differences = np.diff(f)
    width = float(differences[0])
    if width <= 0 or not np.allclose(differences, width, rtol=1e-8, atol=abs(width)*1e-12):
        raise ValueError("Frequency axis must be strictly increasing and uniformly spaced")
    if len(analysis_band_hz) != 2:
        raise ValueError("analysis_band_hz must have two endpoints")
    low, high = (_scalar(v, "analysis band endpoint") for v in analysis_band_hz)
    if low >= high or low < f[0]-width/2 or high > f[-1]+width/2:
        raise ValueError("Analysis band must be nonempty and inside the available bin cells")
    fraction = _scalar(occupied_fraction, "occupied_fraction")
    floor = _scalar(noise_floor_psd, "noise_floor_psd")
    threshold = _scalar(min_effective_power, "min_effective_power")
    lo = None if rf_lo_hz is None else _scalar(rf_lo_hz, "rf_lo_hz")
    if not 0 < fraction <= 1 or floor < 0 or threshold < 0 or (lo is not None and lo < 0):
        raise ValueError("Invalid fraction, noise floor, power threshold or RF LO")

    left = np.maximum(f-width/2, low)
    right = np.minimum(f+width/2, high)
    overlap = np.maximum(right-left, 0)
    with np.errstate(over="ignore", invalid="ignore"):
        observed = float(np.sum(density*overlap))
        mass = np.maximum(density-floor, 0)*overlap
        total = float(np.sum(mass))
    if not np.isfinite(observed) or not np.isfinite(total):
        raise ValueError("Integrated region power exceeds the floating-point range")
    common = dict(observed_region_power=observed, effective_region_power=total,
                  occupied_fraction=fraction, analysis_band_hz=(low, high),
                  bin_width_hz=width, noise_floor_psd=floor, min_effective_power=threshold)
    if total <= threshold:
        return OccupiedBandwidth(status="no_effective_power" if total == 0 else "below_power_threshold",
                                 lower_hz=None, upper_hz=None, bandwidth_hz=None,
                                 center_baseband_hz=None, center_rf_hz=None, **common)

    active = np.flatnonzero(mass > 0)
    cumulative = np.cumsum(mass[active])
    # Use the same summation result as the CDF to keep its endpoint consistent.
    cdf_total = float(cumulative[-1])

    def quantile(q):
        target = q*cdf_total
        pos = min(int(np.searchsorted(cumulative, target, side="left")), len(active)-1)
        index = active[pos]
        previous = 0.0 if pos == 0 else float(cumulative[pos-1])
        within = float(np.clip((target-previous)/mass[index], 0, 1))
        return float(left[index]+within*(right[index]-left[index]))

    tail = (1-fraction)/2
    lower, upper = quantile(tail), quantile(1-tail)
    center = (lower+upper)/2
    return OccupiedBandwidth(status="ok", lower_hz=lower, upper_hz=upper,
                             bandwidth_hz=upper-lower, center_baseband_hz=center,
                             center_rf_hz=None if lo is None else lo+center, **common)


def rrc_occupied_bandwidth_hz(occupied_fraction: float, symbol_rate_hz: float,
                              rolloff: float) -> float:
    """Analytic two-sided occupied bandwidth of an ideal RRC-shaped spectrum.

    The magnitude of a root-raised-cosine filter squared is a raised-cosine
    spectrum, so the transmitted PSD is exactly::

        P(f) = 1                                    |f| <= a
        P(f) = 0.5[1 + cos(pi(|f|-a)/(beta*Rs))]    a < |f| <= (1+beta)Rs/2
        P(f) = 0                                    otherwise
        a = (1-beta)Rs/2

    Total two-sided power is Rs. Two facts are easy to confuse:

    * ``Rs*(1+beta)`` is the **support**: the width at which the spectrum has
      fallen to zero. It is NOT the 99% containment bandwidth.
    * The 99% containment bandwidth is narrower. At beta=0.35 and Rs=240 ksym/s
      the support is 324 kHz but the 99% width is about 280 kHz.

    This function solves for the containment width, which is the quantity a
    spectrum analyser's OBW measurement reports and the quantity to compare a
    measured 99% bandwidth against.

    ``occupied_fraction`` is the two-sided fraction of total power (0, 1].
    """
    fraction = _scalar(occupied_fraction, "occupied_fraction")
    rs = _scalar(symbol_rate_hz, "symbol_rate_hz")
    beta = _scalar(rolloff, "rolloff")
    if not 0 < fraction <= 1:
        raise ValueError("occupied_fraction must be in (0, 1]")
    if rs <= 0:
        raise ValueError("symbol_rate_hz must be positive")
    if not 0 <= beta <= 1:
        raise ValueError("rolloff must be in [0, 1]")

    if beta == 0:
        # Rectangular spectrum of width Rs: containment scales linearly.
        return fraction * rs
    flat_half = (1-beta)*rs/2
    roll_width = beta*rs
    # Fraction inside the flat region is (1-beta) of the total. While the
    # containment edge is still inside the flat part, width = 2x and
    # fraction = 2x/Rs, hence width = fraction*Rs.
    target = fraction-(1-beta)
    if target <= 0:
        return fraction*rs
    # The roll-off can supply at most beta of the total per unit, so a target
    # beyond beta cannot be reached before the support ends.
    if target >= beta:
        return rs*(1+beta)

    def energy(u):
        return 0.5*(u+roll_width/np.pi*np.sin(np.pi*u/roll_width))

    # energy() rises monotonically from 0 to roll_width/2 on [0, roll_width].
    lo, hi = 0.0, roll_width
    goal = target*rs/2
    for _ in range(200):
        mid = 0.5*(lo+hi)
        if energy(mid) < goal:
            lo = mid
        else:
            hi = mid
    return 2*(flat_half+0.5*(lo+hi))
