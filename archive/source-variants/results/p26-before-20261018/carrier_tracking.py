"""Decision-directed carrier tracking for the received PSK/QAM constellations.

The loop corrects residual carrier phase/frequency inside a contiguous symbol
sequence. It does not repair missing samples. EXP-HW-014 found that the older
p21 long captures had source-position jumps at DMA buffer boundaries; their
poor long-block constellations were not evidence of oscillator drift alone.

This module keeps the samples and tracks the drift instead: a second-order
decision-directed phase-locked loop running at the symbol rate, with decisions
taken against a nominal constellation.

Scope: carrier phase only. Timing, DMA continuity, phase ambiguity and any
physical oscillator calibration are the caller's responsibility.
"""

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike, NDArray

# Floor for the EVM ratio, far below any physically meaningful error.
RELATIVE_FLOOR = 1e-15



def _normalized(points: NDArray[np.complex128]) -> NDArray[np.complex128]:
    power = float(np.mean(np.abs(points) ** 2))
    if power <= 0:
        raise ValueError("constellation must have non-zero power")
    return points / np.sqrt(power)


def _build_constellations() -> dict[str, NDArray[np.complex128]]:
    bpsk = np.array([1 + 0j, -1 + 0j])
    qpsk = np.array([1 + 1j, -1 + 1j, -1 - 1j, 1 - 1j])
    levels = np.array([-3, -1, 1, 3], dtype=np.float64)
    qam16 = np.array([i + 1j * q for i in levels for q in levels])
    return {
        "bpsk": _normalized(bpsk),
        "qpsk": _normalized(qpsk),
        "qam16": _normalized(qam16),
    }


CONSTELLATIONS = _build_constellations()
ALIASES = {
    "16qam": "qam16",
    "qam-16": "qam16",
    "qam": "qam16",
}


def constellation(name: str) -> NDArray[np.complex128]:
    """Return the unit-average-power constellation points for a modulation name."""
    key = str(name).strip().lower()
    key = ALIASES.get(key, key)
    if key not in CONSTELLATIONS:
        raise ValueError(f"unknown modulation {name!r}; expected one of {sorted(CONSTELLATIONS)}")
    return CONSTELLATIONS[key]


@dataclass(frozen=True)
class TrackingResult:
    corrected: NDArray[np.complex128]
    phase_rad: NDArray[np.float64]
    frequency_rad_per_symbol: NDArray[np.float64]
    error_rad: NDArray[np.float64]
    locked_from: int


def _loop_gains(loop_bw: float, damping: float) -> tuple[float, float]:
    """Second-order loop gains from a normalised loop bandwidth.

    ``loop_bw`` is in units of the symbol rate; 0.01 is a slow, narrow loop and
    0.05 a fast one. The standard relations are used so the damping stays
    interpretable.
    """
    if not 0 < loop_bw < 0.5:
        raise ValueError("loop_bw must be in (0, 0.5)")
    if damping <= 0:
        raise ValueError("damping must be positive")
    theta = loop_bw / damping
    denom = 1 + 2 * damping * theta + theta ** 2
    k1 = 4 * damping * theta / denom
    k2 = 4 * theta ** 2 / denom
    return k1, k2


def track_carrier(
    symbols: ArrayLike,
    points: ArrayLike,
    loop_bw: float = 0.02,
    damping: float = 0.707,
    initial_phase: float = 0.0,
    max_error_rad: float = 0.6,
) -> TrackingResult:
    """Run a decision-directed second-order PLL over symbol-rate samples.

    ``max_error_rad`` clips the per-symbol phase error. Without a clip, one
    symbol decided into the wrong quadrant injects a large error and the loop
    can be thrown off; clipping keeps a single bad decision from breaking lock.
    """
    x = np.asarray(symbols, dtype=np.complex128)
    if x.ndim != 1 or x.size == 0:
        raise ValueError("symbols must be a non-empty 1-D array")
    if not np.isfinite(x).all():
        raise ValueError("symbols must be finite")
    table = np.asarray(points, dtype=np.complex128)
    if table.ndim != 1 or table.size == 0:
        raise ValueError("points must be a non-empty 1-D array")
    if not np.all(np.isfinite(table)):
        raise ValueError("points must be finite")

    if not np.isfinite(initial_phase) or not np.isfinite(max_error_rad) or max_error_rad <= 0:
        raise ValueError("initial phase must be finite and max_error_rad positive and finite")
    if not np.isfinite(loop_bw) or not np.isfinite(damping):
        raise ValueError("loop parameters must be finite")
    # Decisions are made against a unit-power constellation. Preserve the
    # caller's output amplitude, but do not let ADC-code magnitude set PLL gain.
    scale = float(np.sqrt(np.mean(abs(x)**2)))
    if scale <= 0:
        raise ValueError("symbols have no usable power")
    table = _normalized(table)
    normalized = x/scale
    k1, k2 = _loop_gains(loop_bw, damping)

    corrected = np.empty_like(x)
    phase = np.empty(x.size, dtype=np.float64)
    freq = np.empty(x.size, dtype=np.float64)
    error = np.empty(x.size, dtype=np.float64)

    phase_state = float(initial_phase)
    integrator = 0.0

    for index, sample in enumerate(normalized):
        rotated = sample * np.exp(-1j * phase_state)
        distances = np.abs(rotated - table) ** 2
        decision = table[int(np.argmin(distances))]
        magnitude = float(np.abs(decision))
        if magnitude < 1e-12 or magnitude != magnitude:
            residual = 0.0
        else:
            residual = float(np.imag(rotated * np.conjugate(decision)) / (magnitude ** 2))
        residual = float(np.clip(residual, -max_error_rad, max_error_rad))

        corrected[index] = rotated*scale
        phase[index] = phase_state
        freq[index] = integrator
        error[index] = residual

        integrator += k2 * residual
        phase_state += k1 * residual + integrator

    return TrackingResult(
        corrected=corrected,
        phase_rad=phase,
        frequency_rad_per_symbol=freq,
        error_rad=error,
        locked_from=0,
    )


def evm_db(symbols: ArrayLike, points: ArrayLike) -> float:
    """Gain-invariant error-vector magnitude in dB (lower is better).

    The signal is first normalised to unit mean power, so the reported figure is
    independent of the capture level.

    This is decision-directed EVM: the carrier phase must already be aligned
    closely enough for nearest-point decisions. The COMPLEX gain fit then hides
    a small constant rotation which does not change those decisions. It does
    NOT guarantee arbitrary-rotation invariance (a 37-degree rotation of 16QAM
    can change the decisions). Use ``reference_evm_db`` with known transmitted
    symbols when assessing absolute quality or phase-ambiguity resolution.
    """
    x = np.asarray(symbols, dtype=np.complex128)
    table = np.asarray(points, dtype=np.complex128)
    if x.ndim != 1 or x.size == 0:
        raise ValueError("symbols must be nonempty and 1-D")
    if table.ndim != 1 or table.size == 0 or not np.isfinite(table).all():
        raise ValueError("points must be a finite, nonempty 1-D array")
    if not np.isfinite(x).all():
        raise ValueError("symbols must be finite")

    # Normalise before deciding. Nearest-point decisions against a unit-power
    # table are only valid near unit power; a scaled-up 16QAM capture would
    # otherwise map inner points onto outer ones and report nonsense.
    scale = float(np.sqrt(np.mean(np.abs(x) ** 2)))
    if scale <= 0 or not np.isfinite(scale):
        raise ValueError("symbols have no usable power")
    x = x / scale

    distances = np.abs(x[:, None] - table[None, :]) ** 2
    decisions = table[np.argmin(distances, axis=1)]

    numerator = complex(np.sum(x * np.conjugate(decisions)))
    denominator = float(np.sum(np.abs(decisions) ** 2))
    if denominator <= 0:
        raise ValueError("degenerate constellation")
    gain = numerator / denominator

    reference = gain * decisions
    error_power = float(np.mean(np.abs(x - reference) ** 2))
    signal_power = float(np.mean(np.abs(reference) ** 2))
    if signal_power <= 0:
        raise ValueError("reference has no power")
    # The floor is relative, not absolute. An absolute floor makes a perfect
    # constellation report -300 dB at one scale and -309 dB at another, which
    # breaks gain invariance in exactly the case the metric is meant to have it.
    ratio = max(error_power / signal_power, RELATIVE_FLOOR)
    return float(10 * np.log10(ratio))


def reference_evm_db(symbols: ArrayLike, expected: ArrayLike) -> float:
    """Data-aided EVM with one complex LS gain; no symbol decisions or PLL.

    Identical-length aligned transmitted symbols must be supplied. Constant
    gain/phase is absorbed, but time-varying phase and waveform errors remain.
    This is an offline known-source measurement, not proof of blind decoding.
    """
    x = np.asarray(symbols,dtype=np.complex128)
    ref = np.asarray(expected,dtype=np.complex128)
    if x.ndim != 1 or ref.ndim != 1 or x.size == 0 or x.shape != ref.shape:
        raise ValueError("symbols and expected must be nonempty aligned 1-D arrays")
    if not np.isfinite(x).all() or not np.isfinite(ref).all() or not np.any(abs(ref)):
        raise ValueError("symbols must be finite and reference must have power")
    gain = np.vdot(ref,x)/np.vdot(ref,ref)
    power = float(np.mean(abs(gain*ref)**2))
    if power <= 0:
        raise ValueError("fitted reference has no power")
    return float(10*np.log10(max(float(np.mean(abs(x-gain*ref)**2))/power,RELATIVE_FLOOR)))


def align_rotation(
    symbols: ArrayLike,
    points: ArrayLike,
    step_deg: float = 0.5,
    symmetry_deg: float = 90.0,
) -> tuple[NDArray[np.complex128], float]:
    """Rotate a constellation to its best orientation, returning symbols and angle.

    Why this exists: stripping the modulation with the M-th power is only valid
    for constant-modulus PSK. For 16QAM the points have several amplitudes, so
    ``unit**4`` does not collapse to one phasor and the recovered angle is
    meaningless. That left a 16QAM capture rotated by an arbitrary angle, the
    nearest-point decisions then failed, and two identical captures scored -10.9
    and -37.3 dB depending only on their initial rotation.

    Searching the rotation directly works for any square constellation: the
    candidate angles span one symmetry period (90 degrees by default), and the
    winner is the one with the lowest blind EVM.
    """
    table = np.asarray(points, dtype=np.complex128)
    if table.ndim != 1 or table.size == 0:
        raise ValueError("points must be a non-empty 1-D array")
    if not 0 < step_deg <= symmetry_deg:
        raise ValueError("step_deg must be positive and no larger than symmetry_deg")
    if symmetry_deg <= 0:
        raise ValueError("symmetry_deg must be positive")

    x = np.asarray(symbols, dtype=np.complex128)
    best_angle = 0.0
    best_evm = np.inf
    for angle_deg in np.arange(0.0, symmetry_deg, step_deg):
        rotated = x * np.exp(-1j * np.deg2rad(angle_deg))
        value = evm_db(rotated, table)
        if value < best_evm:
            best_evm, best_angle = value, float(angle_deg)
    return x * np.exp(-1j * np.deg2rad(best_angle)), best_angle