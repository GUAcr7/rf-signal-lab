import numpy as np
import pytest

from rfsig.power import mean_iq_power, power_db
from rfsig.spectrum import power_periodogram


def test_hand_calculated_constant_complex_and_varying_vectors():
    assert mean_iq_power([3+4j]*7) == 25
    assert mean_iq_power([1, 2j]) == 2.5


def test_int16_is_converted_before_squaring_and_input_is_preserved():
    samples = np.array([32767, -32768], dtype=np.int16)
    before = samples.copy()
    assert mean_iq_power(samples) == 1073709056.5
    assert samples.dtype == np.int16
    np.testing.assert_array_equal(samples, before)
    assert mean_iq_power([2047-2048j]) == 8384513


def test_known_four_phase_tone_has_expected_average_and_reference_db():
    samples = np.tile([0.5, 0.5j, -0.5, -0.5j], 16)
    assert mean_iq_power(samples) == 0.25
    assert power_db(mean_iq_power(samples), 0.25) == 0


@pytest.mark.parametrize("scale,expected_ratio,expected_db", [
    (2, 4, 6.020599913279624),
    (0.5, 0.25, -6.020599913279624),
    (10, 100, 20),
])
def test_amplitude_scaling_has_theoretical_power_and_db_change(scale, expected_ratio, expected_db):
    samples = np.array([3+4j, 1-2j, -2+3j, 0.5j])
    original = mean_iq_power(samples)
    changed = mean_iq_power(scale*samples)
    assert changed == pytest.approx(expected_ratio*original)
    assert power_db(changed, original) == pytest.approx(expected_db, abs=1e-12)


def test_phase_rotation_and_conjugation_preserve_power():
    samples = np.array([1+2j, -3j, 4-1j, -2+2j])
    expected = mean_iq_power(samples)
    assert mean_iq_power(1j*samples) == expected
    assert mean_iq_power(samples*np.exp(1j*0.37)) == pytest.approx(expected)
    assert mean_iq_power(np.conjugate(samples)) == expected


def test_rectangular_spectrum_integral_matches_unwindowed_power():
    samples = np.array([1+3j, 2, -4j, -2+1j, 3-1j, 1j, -1, 2-2j])
    result = power_periodogram(samples, 8000, "rectangular")
    assert result.bin_power.sum() == pytest.approx(mean_iq_power(samples), rel=1e-14)


def test_ai_normalization_removes_original_power_difference():
    first = np.array([1+1j, 2-1j, 0.5j, 3])
    second = first*4
    assert mean_iq_power(second) == 16*mean_iq_power(first)
    first_normalized = first/np.sqrt(mean_iq_power(first))
    second_normalized = second/np.sqrt(mean_iq_power(second))
    assert mean_iq_power(first_normalized) == pytest.approx(1)
    np.testing.assert_allclose(first_normalized, second_normalized)


def test_zero_input_returns_zero_power_and_negative_infinity_db():
    assert mean_iq_power(np.zeros(11, dtype=complex)) == 0
    assert power_db(0, 1) == -np.inf


def test_explicit_reference_and_extreme_finite_ratios():
    assert power_db(1000, 1) == pytest.approx(30)
    assert power_db(1000, 1000) == 0
    assert power_db(1e300, 1e-300) == pytest.approx(6000)
    assert power_db(1e-300, 1e300) == pytest.approx(-6000)


@pytest.mark.parametrize("iq", [[], np.zeros((2, 2)), [np.nan], [1j*np.inf],
                                  ["a"], [True], [1e308]])
def test_rejects_invalid_iq(iq):
    with pytest.raises(ValueError):
        mean_iq_power(iq)


@pytest.mark.parametrize("value,reference", [
    (-1, 1), (1, 0), (1, -1), (np.nan, 1), (1, np.inf),
    (np.inf, 1), (True, 1), (1, False), (1j, 1), ([1], 1),
])
def test_rejects_invalid_power_or_reference(value, reference):
    with pytest.raises(ValueError):
        power_db(value, reference)
