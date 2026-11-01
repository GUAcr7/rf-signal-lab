"""A small floating-point reference for the sampling lesson."""

import numpy as np
from numpy.typing import NDArray


def sample_cosine(
    frequency_hz: float,
    sample_rate_hz: float,
    num_samples: int,
    amplitude: float = 1.0,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Return times in seconds and dimensionless samples of a zero-phase cosine.

    This lesson uses 1 kHz at 16 ksample/s. Selecting sample rates for other
    signals requires the later lesson on aliasing; this is not an RF capture.
    """
    if not np.all(np.isfinite([frequency_hz, sample_rate_hz, amplitude])):
        raise ValueError("frequency, sample rate and amplitude must be finite")
    if frequency_hz < 0 or sample_rate_hz <= 0 or amplitude < 0:
        raise ValueError("frequency/amplitude must be nonnegative; sample rate positive")
    if not isinstance(num_samples, int) or isinstance(num_samples, bool) or num_samples <= 0:
        raise ValueError("num_samples must be a positive integer")

    sample_numbers = np.arange(num_samples, dtype=np.float64)
    times_s = sample_numbers / sample_rate_hz
    samples = amplitude * np.cos(2 * np.pi * frequency_hz * times_s)
    return times_s, samples
