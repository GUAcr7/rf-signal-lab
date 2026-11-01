"""Known-source continuity diagnostics; not a blind receiver or a gap repairer.

A hash verifies transport bytes, not uninterrupted ADC time. Aligning each DMA
buffer to a *known* periodic transmitted waveform reveals skipped source
positions. Advances are modulo the source period: whole lost periods cannot be
counted without timestamps. Do not concatenate buffers whose continuity is unknown.
"""
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ReferenceAlignment:
    source_start: int
    frequency_hz: float
    gain: complex
    correlation: float
    nmse_db: float


def _vector(values, name):
    x = np.asarray(values, dtype=np.complex128)
    if x.ndim != 1 or x.size < 32 or not np.isfinite(x).all():
        raise ValueError(f"{name} must be a finite 1-D array of at least 32 samples")
    if not np.any(abs(x)):
        raise ValueError(f"{name} has no power")
    return x


def align_periodic_reference(samples, reference, sample_rate_hz, initial_frequency_hz,
                             max_refine_hz=10_000.0):
    """Fit source position, one frequency and complex gain within ONE buffer.

    The reference is baseband; ``initial_frequency_hz`` removes the receive
    carrier first. The initial estimate must be close enough for coherent
    correlation (roughly within one inverse buffer duration). Frequency and
    integer delay are refined three times. No resampling, equalisation, symbol
    decisions, arbitrary phase correction per sample or reference substitution
    is performed. A poor match remains a poor match in ``nmse_db``.
    """
    x, ref = _vector(samples, "samples"), _vector(reference, "reference")
    if len(x) > len(ref):
        raise ValueError("buffer cannot exceed the reference period")
    if not np.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise ValueError("sample_rate_hz must be positive and finite")
    if not np.isfinite(initial_frequency_hz):
        raise ValueError("initial_frequency_hz must be finite")
    if not np.isfinite(max_refine_hz) or max_refine_hz <= 0:
        raise ValueError("max_refine_hz must be positive and finite")
    n = np.arange(len(x))
    length = len(ref)
    positions = (-np.arange(length)) % length
    prefix = np.r_[0, np.cumsum(np.tile(abs(ref)**2, 2))]
    energies = prefix[positions+len(x)]-prefix[positions]
    reference_fft = np.conj(np.fft.fft(ref))
    frequency = float(initial_frequency_hz)
    for _ in range(4):
        baseband = x*np.exp(-2j*np.pi*frequency*n/sample_rate_hz)
        corr = np.fft.ifft(np.fft.fft(baseband, n=length)*reference_fft)
        scores = abs(corr)/np.sqrt(np.maximum(energies*np.sum(abs(x)**2), 1e-30))
        peak = int(np.argmax(scores))
        start = int(positions[peak])
        target = ref[(start+n) % length]
        # Average the cross product before unwrapping; zeros in the RRC pulse
        # must not turn a few noisy sample phases into false 2*pi wraps.
        group = max(8, min(128, len(x)//16))
        count = len(x)//group
        cross = (baseband[:count*group]*np.conj(target[:count*group])).reshape(count,group).mean(axis=1)
        times = (np.arange(count)*group+(group-1)/2)/sample_rate_hz
        phase = np.unwrap(np.angle(cross))
        weights = abs(cross)
        slope = np.polyfit(times, phase, 1, w=np.sqrt(weights))[0]
        correction = float(slope/(2*np.pi))
        if abs(frequency+correction-initial_frequency_hz) > max_refine_hz:
            raise ValueError("frequency refinement left the allowed neighbourhood")
        frequency += correction
    # Evaluate at the final frequency and delay, without using the fitted
    # phase slope as an additional time-varying correction.
    baseband = x*np.exp(-2j*np.pi*frequency*n/sample_rate_hz)
    corr = np.fft.ifft(np.fft.fft(baseband,n=length)*reference_fft)
    scores = abs(corr)/np.sqrt(np.maximum(energies*np.sum(abs(x)**2),1e-30))
    peak = int(np.argmax(scores))
    start = int(positions[peak])
    target = ref[(start+n) % length]
    gain = np.vdot(target,baseband)/np.vdot(target,target)
    error = np.mean(abs(baseband-gain*target)**2)
    power = np.mean(abs(gain*target)**2)
    return ReferenceAlignment(start, frequency, complex(gain), float(scores[peak]),
                              float(10*np.log10(max(error/power,1e-15))))


def modulo_gaps(starts, buffer_samples, period_samples):
    """Extra source advance modulo period, NOT a calibrated missing-sample count.

    +/-1 may come from integer-delay estimation. A result near the full period
    can also mean a small negative timing change; callers need a tolerance and
    the complex correlation before deciding a discontinuity exists.
    """
    values = np.asarray(starts)
    if values.ndim != 1 or values.size < 2 or values.dtype.kind not in "iu":
        raise ValueError("starts must contain at least two integer positions")
    if buffer_samples <= 0 or period_samples <= 0:
        raise ValueError("buffer_samples and period_samples must be positive")
    return (np.diff(values.astype(np.int64))-buffer_samples) % period_samples
