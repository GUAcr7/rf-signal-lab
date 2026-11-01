"""Independent numerical checks for the offline floating-point FIR reference."""

import math

import numpy as np
import pytest

from rfsig.fir import FirStream, apply_fir_full, design_lowpass_fir


def direct_sum_convolution(samples, taps):
    """Definition of causal convolution, without np.convolve or the FIR API."""
    return np.array([
        sum(complex(taps[k]) * complex(samples[n-k])
            for k in range(len(taps)) if 0 <= n-k < len(samples))
        for n in range(len(samples) + len(taps) - 1)
    ], dtype=np.complex128)


def response_at(taps, frequency_hz, sample_rate_hz):
    return sum(float(tap) * np.exp(-2j*np.pi*frequency_hz*k/sample_rate_hz)
               for k, tap in enumerate(taps))


def test_short_complex_convolution_has_hand_calculated_asymmetric_answer():
    # y[n] = x[n] + 2*x[n-1] - x[n-2]. A reversed kernel fails this check.
    result = apply_fir_full([1+2j, 3-1j], [1, 2, -1])
    np.testing.assert_array_equal(result, [1+2j, 5+3j, 5-4j, -3+1j])
    assert result.dtype == np.complex128


def test_full_output_preserves_inputs_and_has_both_finite_record_tails():
    samples = np.array([2-3j, -1+2j, 0.5j, 4], dtype=np.complex64)
    taps = np.array([0.5, -0.25, 0.125, 1, -2], dtype=np.float32)
    old_samples, old_taps = samples.copy(), taps.copy()
    result = apply_fir_full(samples, taps)
    assert len(result) == len(samples) + len(taps) - 1
    np.testing.assert_allclose(result, direct_sum_convolution(samples, taps), atol=1e-15)
    np.testing.assert_array_equal(samples, old_samples)
    np.testing.assert_array_equal(taps, old_taps)


def test_design_coefficients_match_analytic_sinc_and_hamming_definition():
    # A separate scalar formula checks normalization and the centered cutoff.
    fs, cutoff, count = 8000, 1000, 7
    values = []
    for index in range(count):
        offset = index - (count - 1)/2
        ideal = 2*cutoff/fs if offset == 0 else math.sin(2*math.pi*cutoff*offset/fs)/(math.pi*offset)
        window = 0.54 - 0.46*math.cos(2*math.pi*index/(count-1))
        values.append(ideal*window)
    expected = np.array(values) / sum(values)
    result = design_lowpass_fir(fs, cutoff, count)
    assert result.dtype == np.float64
    np.testing.assert_allclose(result, expected, rtol=1e-14, atol=1e-15)


def test_design_meets_declared_example_passband_stopband_and_linear_phase():
    fs, count = 1_000_000, 63
    taps = design_lowpass_fir(fs, 150_000, count)
    np.testing.assert_allclose(taps, taps[::-1], rtol=0, atol=2e-16)
    assert taps.sum() == pytest.approx(1, abs=3e-16)
    frequency = np.linspace(0, fs/2, 16385)
    response = np.exp(-2j*np.pi*frequency[:, None]*np.arange(count)/fs) @ taps
    gain = np.abs(response)
    assert np.max(np.abs(20*np.log10(gain[frequency <= 100_000]))) <= 0.1
    assert -20*np.log10(np.max(gain[frequency >= 200_000])) >= 50
    delay = (count-1)//2
    # Removing the known 31-sample delay leaves a real, positive passband.
    compensated = response[frequency <= 100_000]*np.exp(2j*np.pi*frequency[frequency <= 100_000]*delay/fs)
    assert np.max(np.abs(compensated.imag)) < 2e-14
    assert np.min(compensated.real) > 0


def test_impulse_exposes_causal_delay_and_constant_input_reaches_unit_gain():
    taps = design_lowpass_fir(1_000_000, 150_000, 63)
    impulse = apply_fir_full([1+0j], taps)
    np.testing.assert_array_equal(impulse, taps.astype(complex))
    assert np.argmax(np.abs(impulse)) == 31
    samples = np.full(257, 2-3j)
    filtered = apply_fir_full(samples, taps)
    np.testing.assert_allclose(filtered[62:257], 2-3j, rtol=1e-14, atol=1e-14)


@pytest.mark.parametrize("frequency_hz", [62_500, -62_500, 250_000, -250_000])
def test_tone_steady_state_matches_complex_response_and_power(frequency_hz):
    fs = 1_000_000
    taps = design_lowpass_fir(fs, 150_000, 63)
    n = np.arange(4096)
    samples = 0.7*np.exp(2j*np.pi*frequency_hz*n/fs)
    result = apply_fir_full(samples, taps)
    response = response_at(taps, frequency_hz, fs)
    expected = samples[len(taps)-1:] * response
    steady = result[len(taps)-1:len(samples)]
    np.testing.assert_allclose(steady, expected, rtol=1e-10, atol=3e-13)
    assert np.mean(np.abs(steady)**2) == pytest.approx(0.7**2*abs(response)**2, rel=1e-10, abs=1e-15)


def test_irregular_short_blocks_and_explicit_finish_equal_direct_sum():
    rng = np.random.default_rng(802)
    samples = rng.normal(size=89) + 1j*rng.normal(size=89)
    taps = np.array([0.2, -0.1, 0.3, 0.7, -0.5, 0.1, 0.2, -0.25, 0.6])
    stream = FirStream(taps)
    pieces = []
    start = 0
    for length in [1, 2, 1, 7, 3, 21, 1, 53]:
        block = stream.process(samples[start:start+length])
        assert len(block) == length
        assert block.dtype == np.complex128
        pieces.append(block)
        start += length
    assert start == len(samples)
    tail = stream.finish()
    assert len(tail) == len(taps)-1
    np.testing.assert_allclose(np.concatenate([*pieces, tail]), direct_sum_convolution(samples, taps), rtol=1e-14, atol=1e-14)


def test_single_tap_stream_has_no_tail_and_reset_reopens_it():
    stream = FirStream([-2])
    np.testing.assert_array_equal(stream.process([1+3j, -2j]), [-2-6j, 4j])
    assert stream.finish().shape == (0,)
    with pytest.raises(RuntimeError):
        stream.process([])
    with pytest.raises(RuntimeError):
        stream.finish()
    stream.reset()
    np.testing.assert_array_equal(stream.process([3]), [-6])
    assert stream.finish().size == 0


def test_empty_new_stream_finishes_empty_and_empty_blocks_preserve_history():
    stream = FirStream([1, 2, -1])
    assert stream.process([]).dtype == np.complex128
    assert stream.finish().size == 0
    stream.reset()
    first = stream.process([1+2j])
    assert stream.process(np.array([], dtype=complex)).size == 0
    rest = stream.process([3-1j])
    np.testing.assert_array_equal(np.concatenate([first, rest, stream.finish()]), [1+2j, 5+3j, 5-4j, -3+1j])


def test_reset_discards_prior_history_and_coefficients_are_copied():
    taps = np.array([1, 2, -1], dtype=float)
    stream = FirStream(taps)
    taps[:] = 99
    stream.process([10+20j])
    stream.reset()
    np.testing.assert_array_equal(stream.process([1+2j]), [1+2j])
    np.testing.assert_array_equal(stream.finish(), [2+4j, -1-2j])


@pytest.mark.parametrize("invalid", [None, [[1]], [np.nan], [np.inf], [1j*np.inf], ["bad"]])
def test_invalid_process_block_does_not_advance_state(invalid):
    stream = FirStream([1, 2, -1])
    stream.process([1+2j])
    with pytest.raises(ValueError):
        stream.process(invalid)
    np.testing.assert_array_equal(stream.process([3-1j]), [5+3j])
    np.testing.assert_array_equal(stream.finish(), [5-4j, -3+1j])


def test_overflow_is_rejected_without_advancing_stream_state():
    with pytest.raises(ValueError):
        apply_fir_full([1e308, 1e308], [1, 1])
    stream = FirStream([1, 1])
    stream.process([1+2j])
    with pytest.raises(ValueError):
        stream.process([1e308, 1e308])
    np.testing.assert_array_equal(stream.process([3-1j]), [4+1j])
    np.testing.assert_array_equal(stream.finish(), [3-1j])


@pytest.mark.parametrize("taps", [[], [[1]], [np.nan], [np.inf], [1+0.001j], ["bad"], None])
def test_invalid_coefficients_are_rejected_by_both_interfaces(taps):
    with pytest.raises(ValueError):
        apply_fir_full([1+1j], taps)
    with pytest.raises(ValueError):
        FirStream(taps)


def test_zero_imaginary_coefficients_are_accepted_without_discarding_signal_iq():
    np.testing.assert_array_equal(apply_fir_full([1+2j], [2+0j, -1+0j]), [2+4j, -1-2j])


@pytest.mark.parametrize("samples", [[], [[1]], [np.nan], [np.inf], [1j*np.inf], None, ["bad"]])
def test_full_convolution_rejects_invalid_samples(samples):
    with pytest.raises(ValueError):
        apply_fir_full(samples, [1])


@pytest.mark.parametrize("sample_rate_hz,cutoff_hz,tap_count", [
    (0, 1, 3), (-1, 1, 3), (np.inf, 1, 3), (np.nan, 1, 3),
    (True, 0.1, 3), (np.bool_(True), 0.1, 3), ([1000], 100, 3),
    (1+2j, 0.1, 3), (np.complex128(1000+2j), 100, 3),
    (1000, 0, 3), (1000, -1, 3), (1000, 500, 3),
    (1000, 501, 3), (1000, np.nan, 3), (1000, np.inf, 3),
    (1000, True, 3), (1000, np.bool_(True), 3), (1000, [100], 3),
    (1000, 100+2j, 3), (1000, np.complex128(100+2j), 3),
    (1000, 100, 1), (1000, 100, 2),
    (1000, 100, 4), (1000, 100, 3.0), (1000, 100, True),
    (1000, 100, np.bool_(True)), (1000, 100, [3]),
])
def test_design_rejects_invalid_parameters(sample_rate_hz, cutoff_hz, tap_count):
    with pytest.raises(ValueError):
        design_lowpass_fir(sample_rate_hz, cutoff_hz, tap_count)


def test_numpy_real_scalar_design_parameters_and_minimum_length_work():
    result = design_lowpass_fir(np.float64(1000), np.float64(100), np.int64(3))
    assert result.shape == (3,)
    assert np.isfinite(result).all()
    assert result.sum() == pytest.approx(1)


def test_extremely_small_valid_cutoff_remains_finite_and_dc_normalized():
    # As fc/Fs approaches zero, the normalized sinc tends to one. The
    # common 2*fc/Fs amplitude cancels when normalizing to unit DC gain.
    taps = design_lowpass_fir(1e308, 1e-308, 3)
    expected = np.array([0.08, 1, 0.08]) / 1.16
    assert np.isfinite(taps).all()
    np.testing.assert_allclose(taps, expected, rtol=1e-14, atol=1e-15)
