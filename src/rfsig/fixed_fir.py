"""Integer FIR reference; no board access or implicit signal normalization.

Contract: signed 12-bit I/Q counts, signed 18-bit coefficients with 17
fractional bits, signed 36-bit accumulation, ties-to-even rounding and
saturating signed 16-bit output. I and Q occupy columns 0 and 1.
"""

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


INPUT_BITS = 12
COEFFICIENT_BITS = 18
FRACTIONAL_BITS = 17
ACCUMULATOR_BITS = 36
OUTPUT_BITS = 16
MAX_TAPS = 63


@dataclass(frozen=True)
class FixedFirResult:
    """One entry per output sample; saturation flags are per I/Q component."""

    counts: NDArray[np.int16]
    saturated: NDArray[np.bool_]
    accumulators: NDArray[np.int64]


def _integer_array(values, *, name, bits, columns=None, allow_empty=False):
    try:
        array = np.asarray(values)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError(f"{name} must contain signed {bits}-bit integers") from exc
    if columns and allow_empty and array.ndim == 1 and array.size == 0:
        array = np.empty((0, columns), dtype=np.int64)
    if (array.dtype.kind not in "iu" or
            (columns is None and array.ndim != 1) or
            (columns is not None and (array.ndim != 2 or array.shape[1] != columns)) or
            (not allow_empty and not array.size)):
        raise ValueError(f"{name} has an invalid integer shape")
    minimum, maximum = -(1 << (bits - 1)), (1 << (bits - 1)) - 1
    if np.any(array < minimum) or np.any(array > maximum):
        raise ValueError(f"{name} is outside signed {bits}-bit range")
    return array.astype(np.int64, copy=True)


def _taps(taps_q):
    values = _integer_array(taps_q, name="taps_q", bits=COEFFICIENT_BITS)
    if len(values) > MAX_TAPS:
        raise ValueError("taps_q must contain 1 through 63 coefficients")
    return values


def _counts(counts, *, allow_empty=False):
    return _integer_array(counts, name="counts", bits=INPUT_BITS,
                          columns=2, allow_empty=allow_empty)


def quantize_fir_coefficients(taps) -> NDArray[np.int64]:
    """Nearest-even quantization to 18-bit coefficients; reject overflow."""
    try:
        values = np.asarray(taps, dtype=np.complex128)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("taps must be a finite real vector") from exc
    if (values.ndim != 1 or not 1 <= values.size <= MAX_TAPS or
            not np.isfinite(values).all() or np.any(values.imag != 0)):
        raise ValueError("taps must contain 1 through 63 finite real values")
    with np.errstate(over="ignore", invalid="ignore"):
        rounded = np.rint(values.real * (1 << FRACTIONAL_BITS))
    if (not np.isfinite(rounded).all() or np.any(rounded < -131072) or
            np.any(rounded > 131071)):
        raise ValueError("quantized taps exceed signed 18-bit range")
    return rounded.astype(np.int64)


def quantize_iq_counts(iq, counts_per_unit=1024) -> NDArray[np.int16]:
    """Fixed simulation unit conversion, never per-record normalization.

    Every component is rounded to nearest-even and must fit signed 12 bits.
    The default scale is an experiment choice, not ADC volts calibration.
    """
    if (isinstance(counts_per_unit, (bool, np.bool_)) or
            not np.isscalar(counts_per_unit) or np.iscomplexobj(counts_per_unit)):
        raise ValueError("counts_per_unit must be a positive finite real scalar")
    try:
        scale = float(counts_per_unit)
        values = np.asarray(iq, dtype=np.complex128)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("invalid scale or I/Q samples") from exc
    if (not np.isfinite(scale) or scale <= 0 or values.ndim != 1 or
            not values.size or not np.isfinite(values).all()):
        raise ValueError("scale and 1D I/Q samples must be finite and nonempty")
    with np.errstate(over="ignore", invalid="ignore"):
        rounded = np.rint(np.column_stack((values.real, values.imag)) * scale)
    if (not np.isfinite(rounded).all() or np.any(rounded < -2048) or
            np.any(rounded > 2047)):
        raise ValueError("quantized I/Q exceeds signed 12-bit range; no clipping performed")
    return rounded.astype(np.int16)


def round_ties_to_even_shift(value, fractional_bits=FRACTIONAL_BITS) -> int:
    """Exact signed nearest-even division by 2**fractional_bits."""
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)):
        raise ValueError("value must be an integer")
    if (isinstance(fractional_bits, (bool, np.bool_)) or
            not isinstance(fractional_bits, (int, np.integer)) or fractional_bits < 1):
        raise ValueError("fractional_bits must be a positive integer")
    denominator = 1 << int(fractional_bits)
    quotient, remainder = divmod(int(value), denominator)
    half = denominator // 2
    if remainder > half or (remainder == half and quotient % 2 != 0):
        quotient += 1
    return quotient


def quantize_accumulator(value) -> tuple[int, bool]:
    """Round then saturate; accumulator overflow is an error, never wrapping."""
    if (isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)) or
            not -(1 << 35) <= int(value) < (1 << 35)):
        raise ValueError("accumulator must fit signed 36 bits")
    rounded = round_ties_to_even_shift(value)
    clipped = min(32767, max(-32768, rounded))
    return clipped, clipped != rounded


def _result(accumulators) -> FixedFirResult:
    accumulators = np.asarray(accumulators, dtype=np.int64)
    if np.any(accumulators < -(1 << 35)) or np.any(accumulators >= (1 << 35)):
        raise ValueError("FIR accumulator overflow; no streaming state was advanced")
    divisor = 1 << FRACTIONAL_BITS
    quotient, remainder = np.divmod(accumulators, divisor)
    rounded = quotient + ((remainder > divisor // 2) |
                          ((remainder == divisor // 2) & ((quotient & 1) != 0)))
    saturated = (rounded < -32768) | (rounded > 32767)
    return FixedFirResult(np.clip(rounded, -32768, 32767).astype(np.int16),
                          saturated, accumulators.copy())


def _convolve(counts, taps_q):
    # All valid 63-tap, 12x18-bit sums fit signed 36 bits, hence also int64.
    return np.column_stack([np.convolve(counts[:, column], taps_q, mode="full")
                            for column in range(2)])


def apply_fixed_fir_full(counts, taps_q) -> FixedFirResult:
    """Zero-history causal full convolution, including M-1 trailing samples."""
    return _result(_convolve(_counts(counts), _taps(taps_q)))


class FixedFirStream:
    """Integer reference for contiguous blocks; reset separates records."""

    def __init__(self, taps_q):
        self._taps = _taps(taps_q)
        self.reset()

    def reset(self) -> None:
        self._history = np.zeros((len(self._taps) - 1, 2), dtype=np.int64)
        self._has_input = False
        self._closed = False

    def process(self, counts) -> FixedFirResult:
        if self._closed:
            raise RuntimeError("FIR stream is finished; call reset")
        values = _counts(counts, allow_empty=True)
        if not len(values):
            return _result(np.empty((0, 2), dtype=np.int64))
        history_length = len(self._history)
        extended = np.concatenate((self._history, values), axis=0)
        accumulators = _convolve(extended, self._taps)
        result = _result(accumulators[history_length:history_length + len(values)])
        self._history = extended[-history_length:].copy() if history_length else extended[:0].copy()
        self._has_input = True
        return result

    def finish(self) -> FixedFirResult:
        if self._closed:
            raise RuntimeError("FIR stream is already finished")
        if self._has_input and len(self._history):
            result = self.process(np.zeros((len(self._history), 2), dtype=np.int16))
        else:
            result = _result(np.empty((0, 2), dtype=np.int64))
        self._closed = True
        return result
