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
