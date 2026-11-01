"""A known complex single tone for RF-loopback reference experiments."""

import numpy as np
from numpy.typing import NDArray


def complex_tone(
    sample_rate_hz: float,
    sample_count: int,
    frequency_offset_hz: float,
    amplitude: float = 0.5,
    initial_phase_rad: float = 0.0,
) -> NDArray[np.complex128]:
    """Return x[n] = A exp(j(2*pi*f*n/fs + phase)) in normalized units."""
    if not np.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise ValueError("sample_rate_hz must be positive and finite")
    if isinstance(sample_count, bool) or not isinstance(sample_count, int) or sample_count <= 0:
        raise ValueError("sample_count must be a positive integer")
    if not np.isfinite(frequency_offset_hz) or abs(frequency_offset_hz) >= sample_rate_hz / 2:
        raise ValueError("frequency_offset_hz must be inside the Nyquist interval")
    if not np.isfinite(amplitude) or not 0 < amplitude <= 1:
        raise ValueError("amplitude must be in (0, 1] normalized units")
    if not np.isfinite(initial_phase_rad):
        raise ValueError("initial_phase_rad must be finite")

    n = np.arange(sample_count, dtype=np.float64)
    phase = initial_phase_rad + 2 * np.pi * frequency_offset_hz * n / sample_rate_hz
    return np.asarray(amplitude * np.exp(1j * phase), dtype=np.complex128)
