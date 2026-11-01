"""Independent integer, analytic and state checks for the fixed FIR contract."""

from fractions import Fraction

import numpy as np
import pytest

from rfsig.fir import design_lowpass_fir
from rfsig.fixed_fir import (
    FixedFirStream, apply_fixed_fir_full, quantize_accumulator,
    quantize_fir_coefficients, quantize_iq_counts, round_ties_to_even_shift,
)


def direct_integer_oracle(samples, taps):
    """Python integer definition plus Fraction's independent ties-even round."""
    accumulators, output, saturation = [], [], []
    for n in range(len(samples) + len(taps) - 1):
        pair = [sum(int(taps[k]) * int(samples[n-k][c])
                    for k in range(len(taps)) if 0 <= n-k < len(samples))
                for c in range(2)]
        rounded = [round(Fraction(value, 131072)) for value in pair]
        clipped = [min(32767, max(-32768, value)) for value in rounded]
        accumulators.append(pair)
        output.append(clipped)
        saturation.append([a != b for a, b in zip(rounded, clipped)])
    return (np.asarray(accumulators, dtype=np.int64), np.asarray(output, dtype=np.int16),
            np.asarray(saturation, dtype=bool))


def assert_oracle(result, samples, taps):
    accumulators, output, saturation = direct_integer_oracle(samples, taps)
    np.testing.assert_array_equal(result.accumulators, accumulators)
    np.testing.assert_array_equal(result.counts, output)
    np.testing.assert_array_equal(result.saturated, saturation)


def test_asymmetric_hand_calculation_detects_tap_order_iq_sign_and_tail_errors():
    samples = [[8, 16], [24, -8]]
    taps = [65536, -32768, 16384]  # [1/2, -1/4, 1/8]
    result = apply_fixed_fir_full(samples, taps)
    np.testing.assert_array_equal(result.counts, [[4, 8], [10, -8], [-5, 4], [3, -1]])
    assert result.counts.dtype == np.int16
    assert result.accumulators.dtype == np.int64
    assert result.saturated.dtype == np.bool_
    assert not result.saturated.any()
    assert_oracle(result, samples, taps)


@pytest.mark.parametrize("accumulator,expected", [
    (0, 0), (65535, 0), (65536, 0), (65537, 1),
    (196607, 1), (196608, 2), (196609, 2), (327680, 2),
    (-65535, 0), (-65536, 0), (-65537, -1),
    (-196607, -1), (-196608, -2), (-196609, -2), (-327680, -2),
])
def test_positive_and_negative_half_cases_round_to_even(accumulator, expected):
    assert round_ties_to_even_shift(accumulator) == expected
    assert quantize_accumulator(accumulator) == (expected, False)


def test_round_then_saturate_boundaries_including_asymmetric_negative_tie():
    scale = 131072
    assert quantize_accumulator(32767 * scale) == (32767, False)
    assert quantize_accumulator(32767 * scale + scale//2 - 1) == (32767, False)
    assert quantize_accumulator(32767 * scale + scale//2) == (32767, True)
    assert quantize_accumulator(-32768 * scale - scale//2) == (-32768, False)
    assert quantize_accumulator(-32768 * scale - scale//2 - 1) == (-32768, True)
    assert quantize_accumulator((1 << 35)-1) == (32767, True)
    assert quantize_accumulator(-(1 << 35)) == (-32768, True)


@pytest.mark.parametrize("value", [1 << 35, -(1 << 35)-1, 1.0, True, np.nan])
def test_accumulator_overflow_and_noninteger_values_are_rejected(value):
    with pytest.raises(ValueError):
        quantize_accumulator(value)


def test_random_rounding_matches_independent_rational_arithmetic():
    rng = np.random.default_rng(70701)
    for value in rng.integers(-(1 << 35), 1 << 35, size=257):
        assert round_ties_to_even_shift(value) == round(Fraction(int(value), 131072))


def test_zero_positive_negative_impulses_and_near_fullscale_counts():
    taps = quantize_fir_coefficients(design_lowpass_fir(1e6, 150e3, 63))
    for samples in (np.zeros((17, 2), dtype=int), [[2047, -2048]], [[-2048, 2047]],
                    np.tile([[2047, -2048], [-2048, 2047]], (40, 1))):
        result = apply_fixed_fir_full(samples, taps)
        assert_oracle(result, samples, taps)
        assert not result.saturated.any()


def test_worst_legal_product_and_accumulation_stay_in_36_bits():
    samples = np.full((80, 2), -2048, dtype=np.int16)
    taps = np.full(63, -131072, dtype=np.int64)
    result = apply_fixed_fir_full(samples, taps)
    expected_peak = 63 * 2048 * 131072
    assert int(result.accumulators.max()) == expected_peak
    assert expected_peak < (1 << 35)
    assert np.all(result.counts[62:80] == 32767)
    assert np.all(result.saturated[62:80])
    assert_oracle(result, samples, taps)


def test_custom_positive_and_negative_output_saturation_are_per_component():
    taps = np.full(63, 131071, dtype=np.int64)
    samples = np.tile([2047, -2048], (80, 1))
    result = apply_fixed_fir_full(samples, taps)
    np.testing.assert_array_equal(result.counts[62], [32767, -32768])
    assert result.saturated[62].all()
    assert_oracle(result, samples, taps)


def test_fixed_input_scale_and_coefficient_quantization_use_ties_to_even():
    samples = np.array([0.5+1.5j, 2.5-3.5j]) / 1024
    np.testing.assert_array_equal(quantize_iq_counts(samples), [[0, 2], [2, -4]])
    taps = np.array([0.5, 1.5, 2.5, -0.5, -1.5, -2.5]) / 131072
    np.testing.assert_array_equal(quantize_fir_coefficients(taps), [0, 2, 2, 0, -2, -2])
    np.testing.assert_array_equal(quantize_iq_counts([1-1j, 0.5+0.25j]),
                                  [[1024, -1024], [512, 256]])


def test_lowpass_quantized_response_keeps_predeclared_float_specification():
    h = design_lowpass_fir(1e6, 150e3, 63)
    taps = quantize_fir_coefficients(h)
    np.testing.assert_array_equal(taps, taps[::-1])
    assert abs(h - taps / 131072).max() <= 0.5/131072
    assert taps.sum() == 131072
    frequency = np.linspace(0, 500_000, 16385)
    response = np.exp(-2j*np.pi*frequency[:, None]*np.arange(63)/1e6) @ (taps / 131072)
    db = 20*np.log10(np.maximum(abs(response), 1e-300))
    assert abs(db[frequency <= 100_000]).max() <= 0.1
    assert np.ptp(db[frequency <= 100_000]) <= 0.1
    assert -db[frequency >= 200_000].max() >= 50


def test_same_integer_input_float_error_bound_is_not_fitted_after_testing():
    rng = np.random.default_rng(70702)
    samples = rng.integers(-2048, 2048, size=(513, 2), dtype=np.int16)
    h = design_lowpass_fir(1e6, 150e3, 63)
    taps = quantize_fir_coefficients(h)
    result = apply_fixed_fir_full(samples, taps)
    floating = np.column_stack([np.convolve(samples[:, c].astype(float), h) for c in range(2)])
    # Same exact integer samples: coefficient approximation plus <=0.5 count rounding.
    bound = np.max(abs(samples.astype(np.int64))) * np.sum(abs(taps/131072 - h)) + 0.5
    assert np.max(abs(result.counts.astype(float) - floating)) <= bound + 1e-10
    assert not result.saturated.any()
    assert_oracle(result, samples, taps)


def test_irregular_contiguous_blocks_finish_and_reset_match_full_integer_oracle():
    rng = np.random.default_rng(70703)
    samples = rng.integers(-2048, 2048, size=(89, 2), dtype=np.int16)
    taps = np.array([65536, -32768, 16384, -8192, 4096, -2048, 1024])
    stream = FixedFirStream(taps)
    pieces, start = [], 0
    for length in (1, 2, 1, 7, 3, 21, 1, 53):
        pieces.append(stream.process(samples[start:start+length]))
        assert len(pieces[-1].counts) == length
        assert stream.process([]).counts.shape == (0, 2)
        start += length
    pieces.append(stream.finish())
    assert len(pieces[-1].counts) == len(taps)-1
    expected_acc, expected_output, expected_sat = direct_integer_oracle(samples, taps)
    np.testing.assert_array_equal(np.concatenate([p.accumulators for p in pieces]), expected_acc)
    np.testing.assert_array_equal(np.concatenate([p.counts for p in pieces]), expected_output)
    np.testing.assert_array_equal(np.concatenate([p.saturated for p in pieces]), expected_sat)
    with pytest.raises(RuntimeError):
        stream.process([])
    with pytest.raises(RuntimeError):
        stream.finish()
    stream.reset()
    np.testing.assert_array_equal(stream.process(samples[:1]).counts, expected_output[:1])


def test_single_tap_empty_stream_and_copied_coefficients():
    taps = np.array([-131072])
    stream = FixedFirStream(taps)
    taps[:] = 0
    assert stream.finish().counts.shape == (0, 2)
    stream.reset()
    np.testing.assert_array_equal(stream.process([[-2048, 2047]]).counts, [[2048, -2047]])
    assert stream.finish().counts.shape == (0, 2)


@pytest.mark.parametrize("invalid", [None, [1, 2], [[1]], [[1, 2, 3]], [[1.0, 2.0]],
                                        [[True, False]], [[2048, 0]], [[0, -2049]],
                                        [[np.nan, 0]], [[1+0j, 2+0j]], [[2**63, 0]]])
def test_invalid_block_rejected_without_advancing_history(invalid):
    stream = FixedFirStream([65536, -32768, 16384])
    stream.process([[8, 16]])
    with pytest.raises(ValueError):
        stream.process(invalid)
    np.testing.assert_array_equal(stream.process([[24, -8]]).counts, [[10, -8]])
    np.testing.assert_array_equal(stream.finish().counts, [[-5, 4], [3, -1]])


@pytest.mark.parametrize("invalid", [[], [1.0], [[1]], [True], [131072], [-131073],
                                        [np.nan], [1j], [0]*64, None])
def test_invalid_quantized_coefficients_rejected(invalid):
    with pytest.raises(ValueError):
        apply_fixed_fir_full([[0, 0]], invalid)
    with pytest.raises(ValueError):
        FixedFirStream(invalid)


@pytest.mark.parametrize("invalid", [[], [[1]], [1], [-1.1], [np.nan], [np.inf], [1j], [0]*64])
def test_invalid_floating_coefficients_do_not_silently_clip(invalid):
    with pytest.raises(ValueError):
        quantize_fir_coefficients(invalid)


@pytest.mark.parametrize("iq,scale", [([], 1024), ([[1]], 1024), ([np.nan], 1024),
                                     ([np.inf], 1024), ([2], 1024), ([-2.001], 1024),
                                     ([1], 0), ([1], -1), ([1], True), ([1], [1]),
                                     ([1], 1j), ([1], np.inf)])
def test_invalid_or_overrange_simulation_samples_are_rejected(iq, scale):
    with pytest.raises(ValueError):
        quantize_iq_counts(iq, scale)
