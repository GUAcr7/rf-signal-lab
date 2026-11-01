"""Unwindowed digital I/Q power and explicit-reference logarithmic ratios.

Input-unit squared is retained: raw receive counts do not imply watts/dBm.
DC and noise are included. Compute before per-frame AI normalization.
"""

from numbers import Real

import numpy as np
from numpy.typing import ArrayLike


def mean_iq_power(iq: ArrayLike) -> float:
    """Return mean(I**2+Q**2); do not mutate or normalize the input.

    Real numeric arrays represent Q=0. Conversion precedes squaring so int16
    values do not overflow their integer container. Reject unrepresentable
    floating results instead of returning infinite power.
    """
    array = np.asarray(iq)
    if array.ndim != 1 or array.size == 0 or array.dtype.kind not in "iufc":
        raise ValueError("I/Q must be a nonempty numeric one-dimensional array")
    array = array.astype(np.complex128)
    if not np.isfinite(array).all():
        raise ValueError("I/Q must contain finite samples")
    with np.errstate(over="ignore", invalid="ignore"):
        value = float(np.mean(array.real**2+array.imag**2))
    if not np.isfinite(value):
        raise ValueError("Digital power exceeds the supported floating-point range")
    return value


def _real_scalar(value, name):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a finite real scalar")
    value = float(value)
    if not np.isfinite(value):
        raise ValueError(f"{name} must be a finite real scalar")
    return value


def power_db(power: float, reference_power: float) -> float:
    """Return 10*log10(power/reference_power); reference must be explicit.

    A zero numerator returns -inf, not a fabricated finite display floor.
    Subtract logarithms to avoid ratio overflow/underflow for finite scalars.
    Caller records units/reference and interprets receiver gain separately.
    """
    value = _real_scalar(power, "power")
    reference = _real_scalar(reference_power, "reference_power")
    if value < 0 or reference <= 0:
        raise ValueError("power must be nonnegative and reference_power must be positive")
    if value == 0:
        return float("-inf")
    return float(10*(np.log10(value)-np.log10(reference)))
