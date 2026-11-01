import numpy as np
import pytest

from rfsig.saturation import (
    COMPRESSING,
    EXPECTED_STEP_DB,
    LINEAR,
    SATURATED,
    UNEXPECTED_GAIN,
    analyse_steps,
    iq_power_stats,
    judge_step,
    step_gain_db,
)


def test_expected_step_is_six_db():
    assert EXPECTED_STEP_DB == pytest.approx(6.0206, abs=1e-4)


def test_mean_power_of_a_deterministic_signal_is_exact():
    # 3+4j has |x| = 5, so every sample contributes exactly 25.
    stats = iq_power_stats(np.full(256, 3 + 4j))
    assert stats.mean_power == pytest.approx(25.0, rel=1e-15)
    assert stats.rms == pytest.approx(5.0, rel=1e-15)
    assert stats.peak_abs == pytest.approx(5.0, rel=1e-15)
    assert stats.sample_count == 256


def test_mean_power_of_complex_noise_matches_the_variance():
    rng = np.random.default_rng(3)
    iq = (rng.standard_normal(200_000) + 1j * rng.standard_normal(200_000)) / np.sqrt(2)
    stats = iq_power_stats(iq)
    # Finite-sample scatter, so this is a statistical check, not an exact one.
    assert stats.mean_power == pytest.approx(1.0, rel=0.02)
    assert stats.rms == pytest.approx(1.0, rel=0.01)
    # Gaussian complex noise: peak factor sits a bit above 2 in amplitude terms.
    assert 3.0 < stats.crest_factor_db < 15.0


def test_endpoint_fraction_is_none_without_a_full_scale():
    stats = iq_power_stats(np.ones(64, dtype=complex))
    assert stats.endpoint_fraction is None
    assert stats.full_scale is None


def test_endpoint_fraction_detects_clipping():
    # The metric is relative to the declared full scale, so the reference signal
    # is clipped far above its excursions while the compressed one is clipped
    # where a large fraction of samples actually lands.
    sigma = 60.0
    rng = np.random.default_rng(9)
    raw = (rng.standard_normal(200_000) + 1j * rng.standard_normal(200_000)) * sigma

    wide = 1000.0            # ~16 sigma, effectively no clipping
    narrow = 100.0           # ~1.67 sigma, heavy clipping
    clean = np.clip(np.real(raw), -wide, wide) + 1j * np.clip(np.imag(raw), -wide, wide)
    clipped = np.clip(np.real(raw), -narrow, narrow) + 1j * np.clip(np.imag(raw), -narrow, narrow)

    clean_stats = iq_power_stats(clean, full_scale=wide)
    clipped_stats = iq_power_stats(clipped, full_scale=narrow)

    assert clean_stats.endpoint_fraction == 0.0
    assert clipped_stats.endpoint_fraction > 0.10
    # Clipping reduces the measured power relative to the unclipped input.
    assert clipped_stats.mean_power < clean_stats.mean_power * 0.90


def test_step_gain_of_a_doubling_of_power_is_three_db():
    # Doubling POWER is +3.01 dB; doubling AMPLITUDE is +6.02 dB.
    assert step_gain_db(2.0, 1.0) == pytest.approx(3.0103, abs=1e-4)


def test_step_gain_of_a_doubling_of_amplitude_is_the_expected_step():
    # The 64/128/256/512 waveform family doubles the amplitude, so power x4.
    assert step_gain_db(4.0, 1.0) == pytest.approx(EXPECTED_STEP_DB, rel=1e-12)
    assert step_gain_db(1.0, 1.0) == pytest.approx(0.0, abs=1e-12)
    assert step_gain_db(0.25, 1.0) == pytest.approx(-EXPECTED_STEP_DB, rel=1e-12)


@pytest.mark.parametrize("measured,verdict", [
    (6.02, LINEAR),
    (6.50, LINEAR),
    (5.60, LINEAR),          # 5.60 >= 6.0206-0.5 = 5.5206
    (5.40, COMPRESSING),     # below the linear band but above the saturated margin
    (2.00, COMPRESSING),
    (0.50, SATURATED),
    (-1.00, SATURATED),
])
def test_judge_step_classification(measured, verdict):
    assert judge_step(measured) == verdict


def test_judge_step_rejects_non_finite_and_negative_tolerances():
    with pytest.raises(ValueError):
        judge_step(float("nan"))
    with pytest.raises(ValueError):
        judge_step(6.0, tolerance_db=-0.1)
    with pytest.raises(ValueError):
        judge_step(6.0, saturated_margin_db=-0.1)


def test_analyse_steps_reports_all_linear_when_power_quadruples_per_step():
    # Each doubling of amplitude multiplies power by 4 -> +6.0206 dB.
    powers = [10.0, 40.0, 160.0, 640.0]
    result = analyse_steps(powers)
    assert result["all_linear"] is True
    assert result["first_non_linear_index"] is None
    assert [round(s["error_db"], 9) for s in result["steps"]] == [0.0, 0.0, 0.0]


def test_analyse_steps_flags_the_first_compressed_step():
    # Linear for two steps, then the third only gains ~3 dB.
    powers = [10.0, 40.0, 160.0, 320.0]
    result = analyse_steps(powers)
    assert result["all_linear"] is False
    assert result["first_non_linear_index"] == 2
    assert result["steps"][2]["verdict"] == COMPRESSING


def test_analyse_steps_marks_severe_saturation():
    powers = [10.0, 40.0, 160.0, 165.0]
    result = analyse_steps(powers)
    assert result["steps"][2]["verdict"] == SATURATED


def test_analyse_steps_rejects_bad_input():
    with pytest.raises(ValueError):
        analyse_steps([1.0])
    with pytest.raises(ValueError):
        analyse_steps([1.0, 0.0])
    with pytest.raises(ValueError):
        analyse_steps([1.0, -2.0])


def test_unexpected_excess_gain_is_not_linear():
    assert judge_step(8.0)==UNEXPECTED_GAIN
    assert not analyse_steps([1,100])["all_linear"]


def test_signed_adc_endpoints_include_both_positive_and_negative_rails():
    iq=np.array([2047+0j,-2048+0j,2046+2047j,2046-2048j,2046+2046j,-2047-2047j])
    stats=iq_power_stats(iq,2048,positive_rail=2047)
    assert stats.endpoint_fraction==pytest.approx(4/6)
    assert stats.endpoint_fraction_both==0
    assert stats.positive_rail==2047


@pytest.mark.parametrize("parameter",[{"tolerance_db":float("nan")},
                                      {"saturated_margin_db":float("inf")},
                                      {"tolerance_db":7}])
def test_invalid_classification_bands_are_rejected(parameter):
    with pytest.raises(ValueError):
        judge_step(6.02,**parameter)


def test_asymmetric_rail_requires_a_valid_negative_rail():
    with pytest.raises(ValueError):
        iq_power_stats(np.ones(8),positive_rail=2047)
