"""Floating-point FIR references for known-rate, contiguous offline samples.

No hardware access, resampling, normalization, synchronization or RF tuning.
Streaming state is valid only across contiguous blocks from the same stream.
Unknown-gap IIO snapshots must not be passed as a contiguous stream.
"""

import numpy as np
from numpy.typing import NDArray


def _positive_rate(value) -> float:
    if isinstance(value, (bool, np.bool_)) or not np.isscalar(value) or np.iscomplexobj(value):
        raise ValueError("sample_rate_hz must be a positive finite scalar")
    try:
        rate = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("sample_rate_hz must be a positive finite scalar") from exc
    if not np.isfinite(rate) or rate <= 0:
        raise ValueError("sample_rate_hz must be a positive finite scalar")
    return rate


def _coefficients(taps) -> NDArray[np.float64]:
    try:
        values = np.asarray(taps, dtype=np.complex128)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("taps must be a nonempty finite real 1D sequence") from exc
    if (values.ndim != 1 or not values.size or not np.isfinite(values).all()
            or np.any(values.imag != 0)):
        raise ValueError("taps must be a nonempty finite real 1D sequence")
    return values.real.copy()


def _samples(iq, *, allow_empty=False) -> NDArray[np.complex128]:
    try:
        values = np.asarray(iq, dtype=np.complex128)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("iq must be a finite 1D sequence") from exc
    if values.ndim != 1 or (not allow_empty and not values.size) or not np.isfinite(values).all():
        raise ValueError("iq must be a finite 1D sequence; full convolution requires samples")
    return values


def _convolve(iq, taps) -> NDArray[np.complex128]:
    with np.errstate(over="ignore", invalid="ignore"):
        result = np.convolve(iq, taps, mode="full")
    if not np.isfinite(result).all():
        raise ValueError("FIR output overflowed; no streaming state was advanced")
    return result


def design_lowpass_fir(sample_rate_hz, cutoff_hz, tap_count) -> NDArray[np.float64]:
    """Odd-length symmetric Hamming-windowed sinc, normalized to H(0)=1.

    cutoff_hz is the ideal sinc cutoff (approximately half-amplitude / -6 dB),
    not a guaranteed passband edge or a -3 dB point. Pass/stop specifications
    need a separate measured frequency-response check for each design.
    The group delay is (tap_count-1)/2 input samples; rate is unchanged.
    """
    rate = _positive_rate(sample_rate_hz)
    if (isinstance(cutoff_hz, (bool, np.bool_)) or not np.isscalar(cutoff_hz)
            or np.iscomplexobj(cutoff_hz)):
        raise ValueError("cutoff_hz must be a finite scalar strictly between 0 and Fs/2")
    try:
        cutoff = float(cutoff_hz)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("cutoff_hz must be a finite scalar strictly between 0 and Fs/2") from exc
    if not np.isfinite(cutoff) or not 0 < cutoff < rate / 2:
        raise ValueError("cutoff_hz must be a finite scalar strictly between 0 and Fs/2")
    if (isinstance(tap_count, (bool, np.bool_))
            or not isinstance(tap_count, (int, np.integer)) or tap_count < 3 or tap_count % 2 == 0):
        raise ValueError("tap_count must be an odd integer >= 3")
    count = int(tap_count)
    offset = np.arange(count, dtype=np.float64) - (count - 1) / 2
    normalized_cutoff = cutoff / rate
    # The common 2*cutoff/Fs factor cancels in DC normalization. Omitting
    # it also avoids all-zero coefficients when that factor underflows.
    taps = np.sinc(2 * normalized_cutoff * offset) * np.hamming(count)
    if not np.isfinite(taps).all() or not np.isfinite(np.sum(taps)) or np.sum(taps) == 0:
        raise ValueError("cutoff/Fs is not representable for this floating-point design")
    return taps / np.sum(taps)


def apply_fir_full(iq, taps) -> NDArray[np.complex128]:
    """Causal full convolution, with zero history and both finite-record tails.

    Output length is len(iq)+len(taps)-1. No implicit delay removal, gain
    fitting, clipping or power normalization is applied.
    """
    return _convolve(_samples(iq), _coefficients(taps))


class FirStream:
    """Stateful causal FIR for contiguous blocks; explicit end-of-record tail.

    process returns one output per input. finish returns the last M-1
    outputs assuming zero beyond the finite record and closes the stream.
    reset starts a new independent record. This is a floating-point reference,
    not a receiver continuity guarantee or a hardware throughput claim.
    """

    def __init__(self, taps):
        self._taps = _coefficients(taps)
        self.reset()

    def reset(self) -> None:
        self._history = np.zeros(len(self._taps) - 1, dtype=np.complex128)
        self._has_input = False
        self._closed = False

    def process(self, iq) -> NDArray[np.complex128]:
        if self._closed:
            raise RuntimeError("FIR stream is finished; call reset before another record")
        values = _samples(iq, allow_empty=True)
        if not values.size:
            return np.empty(0, dtype=np.complex128)
        history_length = len(self._history)
        extended = np.concatenate((self._history, values))
        filtered = _convolve(extended, self._taps)
        result = filtered[history_length:history_length + len(values)].copy()
        self._history = extended[-history_length:].copy() if history_length else extended[:0].copy()
        self._has_input = True
        return result

    def finish(self) -> NDArray[np.complex128]:
        if self._closed:
            raise RuntimeError("FIR stream is already finished")
        if self._has_input and self._history.size:
            result = self.process(np.zeros(len(self._history), dtype=np.complex128))
        else:
            result = np.empty(0, dtype=np.complex128)
        self._closed = True
        return result
