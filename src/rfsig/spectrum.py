"""Two-sided, power-normalized offline I/Q spectrum; no board operations."""

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike, NDArray


@dataclass(frozen=True)
class PowerSpectrum:
    frequency_hz: NDArray[np.float64]
    psd: NDArray[np.float64]
    bin_power: NDArray[np.float64]
    bin_width_hz: float
    sample_count: int
    window: str
    time_mean_power: float
    window_weighted_mean_power: float


def power_periodogram(
    iq: ArrayLike, sample_rate_hz: float, window: str = "hann_periodic"
) -> PowerSpectrum:
    """Return fftshifted PSD in input-unit squared/Hz, retaining DC.

    No input normalization, mean removal, zero padding or truncation is done.
    Sum(psd)*fs/N equals sum(abs(iq)**2*w**2)/sum(w**2).
    For rectangular w, this is also the unweighted time-domain mean power.
    """
    array = np.asarray(iq)
    if array.ndim != 1 or array.size < 4 or array.dtype.kind not in "biufc":
        raise ValueError("I/Q must be a numeric one-dimensional array of at least 4 samples")
    array = array.astype(np.complex128)
    if not np.isfinite(array).all():
        raise ValueError("I/Q must contain finite samples")
    if not np.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise ValueError("sample_rate_hz must be positive and finite")
    sample_rate_hz = float(sample_rate_hz)
    count = array.size
    if window == "rectangular":
        weights = np.ones(count, dtype=np.float64)
    elif window == "hann_periodic":
        weights = 0.5 - 0.5 * np.cos(2 * np.pi * np.arange(count) / count)
    else:
        raise ValueError("window must be rectangular or hann_periodic")
    weight_energy = float(np.sum(weights**2))
    transformed = np.fft.fftshift(np.fft.fft(array * weights))
    psd = np.abs(transformed)**2 / (sample_rate_hz * weight_energy)
    bin_width = sample_rate_hz / count
    sample_power = np.abs(array)**2
    return PowerSpectrum(
        frequency_hz=np.fft.fftshift(np.fft.fftfreq(count, d=1 / sample_rate_hz)),
        psd=psd,
        bin_power=psd * bin_width,
        bin_width_hz=bin_width,
        sample_count=count,
        window=window,
        time_mean_power=float(np.mean(sample_power)),
        window_weighted_mean_power=float(np.sum(sample_power * weights**2) / weight_energy),
    )


def welch_power_spectrum(
    iq: ArrayLike,
    sample_rate_hz: float,
    nperseg: int,
    overlap: float = 0.5,
    window: str = "hann_periodic",
) -> PowerSpectrum:
    """Average the power periodogram over overlapping segments.

    Two-sided and complex-aware, like :func:`power_periodogram`: the individual
    segment PSDs are already power-normalised and are **not** doubled. Doubling
    belongs to the real-signal one-sided convention; applying it to complex I/Q
    inflates every bin except DC and the last one, which distorts both total
    power and any band edge that happens to fall on those bins.

    Averaging PSDs of equal length is the same as averaging |FFT|^2 and then
    scaling once, because every segment shares the same window energy.

    ``time_mean_power`` describes the samples actually covered by the segments,
    which differs from the whole input whenever there is a remainder.
    """
    array = np.asarray(iq)
    if array.ndim != 1 or array.size < 8 or array.dtype.kind not in "biufc":
        raise ValueError("I/Q must be a numeric one-dimensional array of at least 8 samples")
    array = array.astype(np.complex128)
    if not np.isfinite(array).all():
        raise ValueError("I/Q must contain finite samples")
    if not np.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise ValueError("sample_rate_hz must be positive and finite")
    if isinstance(nperseg, bool) or not isinstance(nperseg, (int, np.integer)):
        raise ValueError("nperseg must be an integer")
    if nperseg < 4 or nperseg > array.size:
        raise ValueError("nperseg must be between 4 and the sample count")
    if not 0.0 <= overlap < 1.0:
        raise ValueError("overlap must be in [0, 1)")
    if not np.isfinite(overlap):
        raise ValueError("overlap must be finite")

    nperseg = int(nperseg)
    step = max(1, int(round(nperseg * (1.0 - overlap))))
    segments = 1 + (array.size - nperseg) // step
    if segments < 1:
        raise ValueError("no full segment fits in the input")

    acc = np.zeros(nperseg, dtype=np.float64)
    weighted_sum = 0.0
    for index in range(segments):
        start = index * step
        block = array[start:start + nperseg]
        segment = power_periodogram(block, sample_rate_hz, window)
        acc += segment.psd
        weighted_sum += segment.window_weighted_mean_power

    sample_rate_hz = float(sample_rate_hz)
    bin_width = sample_rate_hz / nperseg
    psd = acc / segments

    # Overlapping segments weigh the overlap region twice, so the mean of the
    # per-segment means is NOT the mean over the covered span. Report the latter
    # directly, and keep the segment-weighted figure for the conservation
    # identity sum(psd)*df == window_weighted_mean_power.
    covered = array[:(segments - 1) * step + nperseg]
    return PowerSpectrum(
        frequency_hz=np.fft.fftshift(np.fft.fftfreq(nperseg, d=1 / sample_rate_hz)),
        psd=psd,
        bin_power=psd * bin_width,
        bin_width_hz=bin_width,
        sample_count=nperseg,
        window=window,
        time_mean_power=float(np.mean(np.abs(covered) ** 2)),
        window_weighted_mean_power=weighted_sum / segments,
    )
