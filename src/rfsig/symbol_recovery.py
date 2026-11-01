"""Recover symbols inside one finite, contiguous PSK/QAM snapshot.

Known modulation, symbol rate and approximate carrier are required. This is a
diagnostic reference, not a blind classifier or a continuous timing loop.
"""
from dataclasses import dataclass

import numpy as np

from rfsig.carrier_tracking import constellation
from rfsig.pulse_shaping import rrc_taps


@dataclass(frozen=True)
class RecoveredSymbols:
    symbols: np.ndarray
    sample_indices: np.ndarray
    timing_offset: int
    phase_rad: float
    guard_samples: int


def recover_snapshot(iq, sample_rate_hz, carrier_hz, modulation,
                     samples_per_symbol=128, rolloff=.35, span_symbols=10,
                     timing_offset=None):
    """Downconvert, matched-filter, drop unsupported edges, pick timing/phase.

    No convolution may cross an unknown DMA boundary. ``sample_indices`` refer
    to the input snapshot, not to a made-up continuous ADC clock. For square
    QPSK/QAM the nominal fourth moment is negative; its phase must be included
    when aligning against the constellation (otherwise QPSK is rotated 45 deg).
    """
    x = np.asarray(iq, dtype=np.complex128)
    if x.ndim != 1 or not np.isfinite(x).all() or not x.size:
        raise ValueError("iq must be a finite, nonempty 1-D array")
    if not np.isfinite(sample_rate_hz) or sample_rate_hz <= 0 or not np.isfinite(carrier_hz):
        raise ValueError("sample rate and carrier must be finite, sample rate positive")
    table = constellation(modulation)
    order = 2 if len(table) == 2 else 4
    taps = rrc_taps(rolloff, span_symbols, samples_per_symbol)
    guard = (len(taps)-1)//2
    if len(x)-2*guard < 16*samples_per_symbol:
        raise ValueError("snapshot too short for filter guards and 16 symbols")
    baseband = x*np.exp(-2j*np.pi*carrier_hz*np.arange(len(x))/sample_rate_hz)
    filtered = np.convolve(baseband,taps,"same")
    best = None
    if timing_offset is not None and (isinstance(timing_offset,bool)
            or not isinstance(timing_offset,(int,np.integer)) or not 0 <= timing_offset < samples_per_symbol):
        raise ValueError("timing_offset must be an integer in [0, samples_per_symbol)")
    offsets = range(samples_per_symbol) if timing_offset is None else [timing_offset]
    for offset in offsets:
        indices = np.arange(offset,len(x),samples_per_symbol)
        indices = indices[(indices >= guard) & (indices < len(x)-guard)]
        power = float(np.mean(abs(filtered[indices])**2))
        if best is None or power > best[0]:
            best = power, offset, indices
    power, offset, indices = best
    if power <= 0:
        raise ValueError("snapshot has no usable power")
    symbols = filtered[indices]
    # Amplitude weighting is intentional; low-SNR pulse zeroes must not count
    # as highly as a symbol near its decision point.
    moment = np.mean(symbols**order)
    nominal_moment = np.mean(table**order)
    phase = float(np.angle(moment/nominal_moment)/order)
    return RecoveredSymbols(symbols*np.exp(-1j*phase), indices, offset, phase, guard)
