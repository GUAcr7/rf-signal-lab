"""Floating-point, offline pulse-shaping references; no hardware access."""

import numpy as np
from numpy.typing import NDArray


def _positive_integer(value: int, name: str) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return int(value)


def _symbols(values) -> NDArray[np.complex128]:
    array = np.asarray(values, dtype=np.complex128)
    if array.ndim != 1 or array.size == 0 or not np.isfinite(array).all():
        raise ValueError("symbols must be a nonempty, finite one-dimensional sequence")
    return array


def hold_symbols(symbols, samples_per_symbol: int) -> NDArray[np.complex128]:
    """Teaching-only rectangular hold: repeat each symbol sps times."""
    sps = _positive_integer(samples_per_symbol, "samples_per_symbol")
    return np.repeat(_symbols(symbols), sps)


def rrc_taps(rolloff: float, span_symbols: int, samples_per_symbol: int) -> NDArray[np.float64]:
    """Symmetric root-raised-cosine FIR with unit energy and odd tap count.

    Time is measured in symbol periods. Length = span*sps+1; group delay
    = span*sps/2 samples. The zero and +/-1/(4*rolloff) limits are explicit.
    Truncation introduces residual ISI; this is not an exact infinite filter.
    """
    span = _positive_integer(span_symbols, "span_symbols")
    sps = _positive_integer(samples_per_symbol, "samples_per_symbol")
    if isinstance(rolloff, (bool, np.bool_)) or not np.isfinite(rolloff) or not 0 <= rolloff <= 1:
        raise ValueError("rolloff must be finite and in [0, 1]")
    if span * sps % 2:
        raise ValueError("span_symbols * samples_per_symbol must be even")
    beta = float(rolloff)
    t = np.arange(-span * sps // 2, span * sps // 2 + 1, dtype=np.float64) / sps
    if beta == 0:
        taps = np.sinc(t)
    else:
        taps = np.empty_like(t)
        zero = t == 0
        singular = np.isclose(np.abs(t), 1 / (4 * beta), rtol=0, atol=1e-14)
        regular = ~(zero | singular)
        u = t[regular]
        taps[regular] = (
            np.sin(np.pi * u * (1 - beta)) + 4 * beta * u * np.cos(np.pi * u * (1 + beta))
        ) / (np.pi * u * (1 - (4 * beta * u) ** 2))
        taps[zero] = 1 + beta * (4 / np.pi - 1)
        taps[singular] = beta / np.sqrt(2) * (
            (1 + 2 / np.pi) * np.sin(np.pi / (4 * beta))
            + (1 - 2 / np.pi) * np.cos(np.pi / (4 * beta))
        )
    return taps / np.sqrt(np.sum(taps**2))


def shape_symbols(symbols, taps, samples_per_symbol: int) -> NDArray[np.complex128]:
    """Zero-insert then full FIR convolution; preserve both transient tails.

    For K symbols and L taps, output length = (K-1)*sps+L.
    Symbols' nominal times are delay+k*sps for symmetric odd-length taps.
    A shaped sample at those times is not generally the original symbol;
    recovery uses a matched filter and accounts for its additional delay.
    """
    sps = _positive_integer(samples_per_symbol, "samples_per_symbol")
    values = _symbols(symbols)
    coeffs = np.asarray(taps, dtype=np.float64)
    if coeffs.ndim != 1 or coeffs.size == 0 or not np.isfinite(coeffs).all():
        raise ValueError("taps must be a nonempty, finite one-dimensional sequence")
    impulses = np.zeros((values.size - 1) * sps + 1, dtype=np.complex128)
    impulses[::sps] = values
    return np.convolve(impulses, coeffs, mode="full")


def normalize_mean_power(iq) -> tuple[NDArray[np.complex128], float]:
    """Normalize this complete offline record to mean |x|^2=1; return scale.

    These units are dimensionless, not ADC counts or RF watts. Do not apply
    this before measuring received relative power.
    """
    values = _symbols(iq)
    power = float(np.mean(np.abs(values)**2))
    if not np.isfinite(power) or power <= 0:
        raise ValueError("mean power must be positive and finite")
    scale = 1 / np.sqrt(power)
    return values * scale, float(scale)
