import numpy as np
import pytest

from rfsig.bpsk import map_bpsk
from rfsig.pulse_shaping import hold_symbols, normalize_mean_power, rrc_taps, shape_symbols


def test_bpsk_hold_matches_hand_sequence():
    result = hold_symbols(map_bpsk([1, 0, 0, 1]), 2)
    np.testing.assert_array_equal(result, [-1, -1, 1, 1, 1, 1, -1, -1])
    assert result.dtype == np.complex128
    assert np.mean(np.abs(result)**2) == 1


def test_fir_convolution_matches_manual_complex_sum():
    # Zero insertion: [1+j, 0, -1+j]; convolve with [1,2,1].
    result = shape_symbols([1+1j, -1+1j], [1, 2, 1], 2)
    np.testing.assert_array_equal(result, [1+1j, 2+2j, 2j, -2+2j, -1+1j])


def test_rrc_beta_one_matches_analytic_limits_and_regular_samples():
    # beta=1: h(0)=4/pi, h(1/4)=1, h(1/2)=4/(3*pi),
    # h(3/4)=0, h(1)=-4/(15*pi), with even symmetry.
    expected = np.array([-4/(15*np.pi), 0, 4/(3*np.pi), 1, 4/np.pi,
                         1, 4/(3*np.pi), 0, -4/(15*np.pi)])
    expected /= np.linalg.norm(expected)
    np.testing.assert_allclose(rrc_taps(1, 2, 4), expected, rtol=0, atol=1e-14)


def test_rrc_has_known_length_delay_symmetry_and_energy():
    taps = rrc_taps(0.35, 10, 8)
    assert len(taps) == 81
    np.testing.assert_allclose(taps, taps[::-1], rtol=0, atol=1e-14)
    np.testing.assert_allclose(np.sum(taps**2), 1, rtol=0, atol=1e-14)
    one_symbol = shape_symbols([1], taps, 8)
    assert int(np.argmax(np.abs(one_symbol))) == 40


def test_matching_rrc_pair_approximately_removes_symbol_interference():
    taps = rrc_taps(0.35, 10, 8)
    combined = np.convolve(taps, taps[::-1])
    # Infinite RRC pair has exact Nyquist zeros; finite 10-symbol span
    # permits 0.015 residual at other symbol times (relative to center=1).
    center = len(combined)//2
    np.testing.assert_allclose(combined[center], 1, rtol=0, atol=1e-14)
    others = np.delete(combined[::8], center//8)
    assert np.max(np.abs(others)) < 0.015


def test_zero_rolloff_is_the_sinc_limit():
    # At whole symbol instants sinc is [0,0,1,0,0].
    np.testing.assert_allclose(rrc_taps(0, 4, 1), [0,0,1,0,0], rtol=0, atol=1e-14)


def test_full_pulse_shaping_keeps_expected_length_and_q_zero():
    result = shape_symbols(map_bpsk([1,0,0,1]), rrc_taps(.35,10,8), 8)
    assert len(result) == 3*8+81
    np.testing.assert_array_equal(result.imag, np.zeros(105))


def test_normalization_known_power_and_phase_preservation():
    result, scale = normalize_mean_power([1+1j, -1-1j])
    np.testing.assert_allclose(scale, 1/np.sqrt(2), rtol=0, atol=1e-14)
    np.testing.assert_allclose(np.mean(np.abs(result)**2), 1, rtol=0, atol=1e-14)
    np.testing.assert_allclose(result[0]/result[1], -1, rtol=0, atol=1e-14)


@pytest.mark.parametrize('sps', [0, -1, 1.5, True])
def test_rejects_invalid_samples_per_symbol(sps):
    with pytest.raises(ValueError):
        hold_symbols([1], sps)


@pytest.mark.parametrize('beta,span,sps', [(-.1,10,8),(1.1,10,8),(np.nan,10,8),(.35,0,8),(.35,3,3)])
def test_rejects_invalid_rrc_parameters(beta,span,sps):
    with pytest.raises(ValueError):
        rrc_taps(beta, span, sps)


@pytest.mark.parametrize('values', [[], [[1,2]], [np.nan], [np.inf]])
def test_rejects_invalid_symbols(values):
    with pytest.raises(ValueError):
        shape_symbols(values, [1], 8)


def test_normalization_rejects_zero_signal():
    with pytest.raises(ValueError):
        normalize_mean_power([0j, 0j])
