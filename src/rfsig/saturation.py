"""Decide whether a receiver chain is still linear from amplitude-step data.

The rule this module implements (and the one the project now documents in
``docs/design/rx-input-budget-20261017.md`` section 5):

    A linear receiver adds exactly 20*log10(2) = 6.0206 dB when input AMPLITUDE
    doubles (power quadruples). Compression shows up as a *smaller* increment, and severe
    saturation as almost no increment at all.

An earlier draft of that document had the sign of this backwards ("halving must
drop more than 6.02 dB"), which would have classified a linear chain as
compressed. Keeping the judgement in code with tests makes that inversion
impossible to reintroduce silently.

Power is the time-domain mean |x|^2 of the captured samples, in ADC-code units
squared. Only ratios matter for the step test, so no calibration is needed.
"""

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike

# 20*log10(2), the increment a doubling of input AMPLITUDE must produce.
EXPECTED_STEP_DB = 20.0 * np.log10(2.0)

LINEAR = "linear"
COMPRESSING = "compressing"
SATURATED = "saturated"
INCREASING = "increasing"
UNEXPECTED_GAIN = INCREASING  # Backward-compatible value; above the linear band.


@dataclass(frozen=True)
class IqPowerStats:
    sample_count: int
    mean_power: float
    rms: float
    peak_abs: float
    crest_factor_db: float
    full_scale: float | None
    endpoint_fraction: float | None
    endpoint_fraction_both: float | None
    positive_rail: float | None = None


def iq_power_stats(iq: ArrayLike, full_scale: float | None = None, *,
                   positive_rail: float | None = None) -> IqPowerStats:
    """Time-domain statistics of a complex capture.

    ``full_scale`` is the magnitude at which the ADC is considered clipped. Pass
    it explicitly; for AD9361 RX the channel is 12-bit sign-extended into 16
    bits, so the natural value is 2048, but that must be confirmed on the actual
    board rather than assumed. Pass ``positive_rail=2047`` with ``full_scale=2048``
    for signed-12 codes: the two rails are asymmetric. Omit positive_rail for a
    symmetric analogue limiter. When ``None`` the endpoint fraction is reported as
    ``None`` instead of being guessed.
    """
    array = np.asarray(iq)
    if array.ndim != 1 or array.size < 2:
        raise ValueError("need a one-dimensional capture of at least 2 samples")
    if array.dtype.kind not in "biufc":
        raise ValueError("capture must be numeric")
    array = array.astype(np.complex128)
    if not np.isfinite(array).all():
        raise ValueError("capture must contain finite samples")

    power = np.abs(array) ** 2
    mean_power = float(np.mean(power))
    peak_abs = float(np.max(np.abs(array)))
    denominator = mean_power if mean_power > 0 else None
    crest_db = float(10.0 * np.log10(peak_abs ** 2 / denominator)) if denominator else float("nan")

    endpoint_fraction = None
    endpoint_both = None
    if positive_rail is not None and (full_scale is None or not np.isfinite(positive_rail)
                                     or positive_rail <= 0):
        raise ValueError("positive_rail requires full_scale and must be positive and finite")
    if full_scale is not None:
        if not np.isfinite(full_scale) or full_scale <= 0:
            raise ValueError("full_scale must be positive and finite")
        limit = float(full_scale)
        i = np.real(array)
        q = np.imag(array)
        upper = float(positive_rail) if positive_rail is not None else limit
        at_i = (i <= -limit) | (i >= upper)
        at_q = (q <= -limit) | (q >= upper)
        endpoint_fraction = float(np.mean(at_i | at_q))
        endpoint_both = float(np.mean(at_i & at_q))

    return IqPowerStats(
        sample_count=int(array.size),
        mean_power=mean_power,
        rms=float(np.sqrt(mean_power)),
        peak_abs=peak_abs,
        crest_factor_db=crest_db,
        full_scale=float(full_scale) if full_scale is not None else None,
        endpoint_fraction=endpoint_fraction,
        endpoint_fraction_both=endpoint_both,
        positive_rail=float(positive_rail) if positive_rail is not None else None,
    )


def step_gain_db(higher_power: float, lower_power: float) -> float:
    """Gain in dB when going from ``lower_power`` to ``higher_power``."""
    for name, value in (("higher_power", higher_power), ("lower_power", lower_power)):
        if not np.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be positive and finite")
    return float(10.0 * np.log10(higher_power / lower_power))


def judge_step(
    measured_db: float,
    tolerance_db: float = 0.5,
    saturated_margin_db: float = 1.0,
) -> str:
    """Classify one amplitude-doubling step.

    ``measured_db`` is what the capture actually showed when the input amplitude was
    doubled. It must be compared against +6.0206 dB: a *smaller* increment means
    compression. (An earlier document draft had this reversed, which would have
    called a linear chain compressed.)
    """
    if not np.isfinite(measured_db):
        raise ValueError("measured_db must be finite")
    if (not np.isfinite(tolerance_db) or not np.isfinite(saturated_margin_db)
            or tolerance_db < 0 or saturated_margin_db < 0
            or saturated_margin_db >= float(EXPECTED_STEP_DB)-tolerance_db):
        raise ValueError("tolerances must be finite, non-negative and leave distinct bands")
    if measured_db > float(EXPECTED_STEP_DB) + tolerance_db:
        return UNEXPECTED_GAIN
    if measured_db >= float(EXPECTED_STEP_DB) - tolerance_db:
        return LINEAR
    if measured_db < saturated_margin_db:
        return SATURATED
    return COMPRESSING


def analyse_steps(
    powers: ArrayLike,
    tolerance_db: float = 0.5,
    saturated_margin_db: float = 1.0,
) -> dict:
    """Run the doubling-step test over a sequence of increasing powers.

    ``powers`` must be ordered from lowest to highest input amplitude, one entry
    per captured segment. Each consecutive pair is treated as a doubling of the
    input amplitude, which is how the 64/128/256/512 waveform set is built.
    """
    values = [float(v) for v in np.asarray(powers, dtype=float).ravel()]
    if len(values) < 2:
        raise ValueError("need at least two power measurements")
    steps = []
    for low, high in zip(values, values[1:]):
        measured = step_gain_db(high, low)
        steps.append({
            "lower_power": low,
            "higher_power": high,
            "measured_gain_db": measured,
            "expected_gain_db": float(EXPECTED_STEP_DB),
            "error_db": measured - float(EXPECTED_STEP_DB),
            "verdict": judge_step(measured, tolerance_db, saturated_margin_db),
        })
    first_bad = next(
        (index for index, step in enumerate(steps) if step["verdict"] != LINEAR),
        None,
    )
    return {
        "expected_gain_db": float(EXPECTED_STEP_DB),
        "tolerance_db": tolerance_db,
        "saturated_margin_db": saturated_margin_db,
        "steps": steps,
        "first_non_linear_index": first_bad,
        "all_linear": first_bad is None,
    }
