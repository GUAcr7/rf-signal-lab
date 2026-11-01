"""Offline consecutive PSD frames and bounded display history.

Time is relative to input sample zero, not hardware or UI wall-clock time.
"""

from collections import deque
from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike, NDArray

from rfsig.spectrum import power_periodogram


def _integer(value, name, minimum):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return int(value)


@dataclass(frozen=True)
class Waterfall:
    frequency_hz: NDArray[np.float64]
    time_seconds: NDArray[np.float64]
    frame_start_samples: NDArray[np.int64]
    psd: NDArray[np.float64]  # [time row, frequency bin]
    sample_rate_hz: float
    fft_size: int
    hop_samples: int
    window: str
    covered_samples: int
    trailing_samples: int


def waterfall_periodogram(
    iq: ArrayLike,
    sample_rate_hz: float,
    fft_size: int = 1024,
    hop_samples: int | None = None,
    window: str = "hann_periodic",
) -> Waterfall:
    """Compute complete contiguous/overlapping frames; never pad the tail.

    The input must be one contiguous sample sequence. This function cannot
    discover acquisition gaps, infer missing samples or stitch separate files.
    """
    count = _integer(fft_size, "fft_size", 4)
    hop = count if hop_samples is None else _integer(hop_samples, "hop_samples", 1)
    if hop > count:
        raise ValueError("hop_samples must not exceed fft_size")
    array = np.asarray(iq)
    if array.ndim != 1 or array.size < count or array.dtype.kind not in "biufc":
        raise ValueError("I/Q must be a numeric 1D sequence with at least fft_size samples")
    # Validate the whole input, including unused tail samples.
    if not np.isfinite(array).all():
        raise ValueError("I/Q must contain finite samples")
    starts = np.arange(0, array.size-count+1, hop, dtype=np.int64)
    frames = [power_periodogram(array[start:start+count], sample_rate_hz, window) for start in starts]
    fs = float(sample_rate_hz)
    covered = int(starts[-1]+count)
    return Waterfall(
        frequency_hz=frames[0].frequency_hz,
        time_seconds=(starts+(count-1)/2)/fs,
        frame_start_samples=starts,
        psd=np.stack([frame.psd for frame in frames]),
        sample_rate_hz=fs,
        fft_size=count,
        hop_samples=hop,
        window=window,
        covered_samples=covered,
        trailing_samples=int(array.size-covered),
    )


class WaterfallHistory:
    """Keep a bounded, chronological display history on one fixed frequency axis.

    Evicted rows count display history, not ADC samples or transmission loss.
    No hardware, GUI, timer, sampling configuration or unit conversion is here.
    """

    def __init__(self, frequency_hz: ArrayLike, max_rows: int = 96):
        self.max_rows = _integer(max_rows, "max_rows", 1)
        frequency = np.asarray(frequency_hz)
        if frequency.ndim != 1 or frequency.size < 4 or frequency.dtype.kind not in "biuf":
            raise ValueError("frequency_hz must be a numeric 1D axis of at least 4 bins")
        frequency = frequency.astype(np.float64)
        if not np.isfinite(frequency).all() or np.any(np.diff(frequency) <= 0):
            raise ValueError("frequency_hz must be finite and strictly increasing")
        self._frequency_hz = frequency.copy()
        self._rows = deque(maxlen=self.max_rows)
        self._times = deque(maxlen=self.max_rows)
        self.rows_received = 0
        self.rows_evicted = 0

    def append(self, psd: ArrayLike, frame_time_seconds: float) -> None:
        row = np.asarray(psd)
        if row.ndim != 1 or row.size != self._frequency_hz.size or row.dtype.kind not in "biuf":
            raise ValueError("PSD row must match the configured frequency bin count")
        if not np.isfinite(row).all() or np.any(row < 0):
            raise ValueError("PSD must be finite and nonnegative")
        if not np.isfinite(frame_time_seconds):
            raise ValueError("frame_time_seconds must be finite")
        time_seconds = float(frame_time_seconds)
        if self._times and time_seconds <= self._times[-1]:
            raise ValueError("frame times must be strictly increasing; reset for a new replay")
        if len(self._rows) == self.max_rows:
            self.rows_evicted += 1
        self._rows.append(row.astype(np.float64, copy=True))
        self._times.append(time_seconds)
        self.rows_received += 1

    def snapshot(self) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]]:
        """Return copied times, frequency axis and PSD [time, frequency]."""
        rows = np.stack(self._rows) if self._rows else np.empty((0, self._frequency_hz.size))
        return np.asarray(self._times, dtype=np.float64), self._frequency_hz.copy(), rows

    def reset(self) -> None:
        """Clear history/counters for the same frequency configuration."""
        self._rows.clear()
        self._times.clear()
        self.rows_received = 0
        self.rows_evicted = 0
