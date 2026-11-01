import json
import struct

import numpy as np
import pytest

from rfsig.tx_waveforms import (
    MAX_SAMPLE_COUNT,
    circular_shape_symbols,
    make_tx_waveform,
    pack_tx_iq_le16,
)


def direct_centered_periodic_fir(symbols, taps, sps):
    """Independent scalar definition, including taps longer than one period."""
    n = len(symbols) * sps
    impulses = [0j] * n
    impulses[::sps] = symbols
    delay = (len(taps) - 1) // 2
    return np.array([
        sum(float(taps[k]) * impulses[(index + delay - k) % n]
            for k in range(len(taps)))
        for index in range(n)
    ])


@pytest.mark.parametrize("taps", [[1, 2, 1], list(range(-7, 8))])
def test_centered_circular_shape_matches_scalar_periodic_sum(taps):
    symbols = [1 + 2j, -3 + 1j, 2 - 1j]
    expected = direct_centered_periodic_fir(symbols, taps, 2)
    np.testing.assert_allclose(circular_shape_symbols(symbols, taps, 2), expected,
                               rtol=0, atol=2e-14)


def test_period_repetition_matches_center_of_long_continuous_fir():
    # Full convolution of nine periods supplies previous/next symbols. Unlike
    # repeating a zero-padded FIR output, this has no startup/tail seam.
    symbols = np.array([1, -1, -1, 1], dtype=complex)
    taps = np.array([0.25, 0.5, 0.75, 1., 0.75, 0.5, 0.25])
    sps = 2
    n = symbols.size * sps
    impulses = np.zeros(9 * n, complex)
    impulses[::sps] = np.tile(symbols, 9)
    continuous = np.convolve(impulses, taps)
    delay = (taps.size - 1) // 2
    expected = continuous[3 * n + delay:6 * n + delay]
    actual = circular_shape_symbols(symbols, taps, sps)
    np.testing.assert_allclose(np.tile(actual, 3), expected, rtol=0, atol=1e-14)


@pytest.mark.parametrize("mode,bits_per_symbol", [("BPSK", 1), ("QPSK", 2), ("16QAM", 4)])
def test_modulated_bits_map_independently_and_periodic_shape_is_quantized(mode, bits_per_symbol):
    result = make_tx_waveform(mode, sample_rate_hz=1_024_000,
                              samples_per_symbol=8, symbol_count=16,
                              digital_peak_counts=1000, seed=19)
    assert result.bits.size == 16 * bits_per_symbol
    bits = result.bits.astype(float).reshape(-1, bits_per_symbol)
    if mode == "BPSK":
        expected_symbols = 1 - 2 * bits[:, 0]
    elif mode == "QPSK":
        expected_symbols = ((1 - 2 * bits[:, 0]) + 1j * (1 - 2 * bits[:, 1])) / np.sqrt(2)
    else:
        levels = {(0, 0): -3, (0, 1): -1, (1, 1): 1, (1, 0): 3}
        expected_symbols = np.array([
            levels[tuple(row[:2])] + 1j * levels[tuple(row[2:])]
            for row in bits
        ]) / np.sqrt(10)
    np.testing.assert_allclose(result.symbols, expected_symbols, rtol=0, atol=1e-15)
    expected_float = direct_centered_periodic_fir(expected_symbols, result.taps, 8)
    scale = result.reference["logical_counts_per_float_unit"]
    expected_iq = np.rint(expected_float.real * scale) + 1j * np.rint(expected_float.imag * scale)
    np.testing.assert_array_equal(result.iq, expected_iq)
    assert len(result.iq) == 128  # No zero-insertion/full-convolution tail.
    assert np.max(np.maximum(abs(result.iq.real), abs(result.iq.imag))) == 1000
    assert result.reference["storage_peak_counts"] == 16000
    assert result.reference["rf_power_dbm"] is None
    assert "not measured 99% OBW" in result.reference["support_definition"]
    json.dumps(result.reference, allow_nan=False)


def test_modulated_offset_matches_integer_bin_carrier_and_support_metadata():
    base = make_tx_waveform("QPSK", sample_rate_hz=1_024_000,
                           samples_per_symbol=8, symbol_count=16, seed=1)
    shifted = make_tx_waveform("QPSK", sample_rate_hz=1_024_000,
                              samples_per_symbol=8, symbol_count=16,
                              seed=1, offset_hz=-128_000)
    unscaled = direct_centered_periodic_fir(base.symbols, base.taps, 8)
    rotated = unscaled * np.exp(2j * np.pi * (-16) * np.arange(128) / 128)
    scale = shifted.reference["logical_counts_per_float_unit"]
    expected = np.rint(rotated.real * scale) + 1j * np.rint(rotated.imag * scale)
    np.testing.assert_array_equal(shifted.iq, expected)
    assert shifted.reference["carrier_cycles_per_buffer"] == -16
    np.testing.assert_allclose(shifted.reference["theoretical_rrc_support_hz"],
                               [-214_400, -41_600], rtol=0, atol=1e-10)


@pytest.mark.parametrize("offset,expected_bin", [(128_000, 64), (-128_000, 448), (0, 0)])
def test_tone_positive_negative_and_dc_have_expected_fft_bin(offset, expected_bin):
    result = make_tx_waveform("tone", sample_rate_hz=1_024_000,
                              samples_per_symbol=8, symbol_count=64,
                              offset_hz=offset, digital_peak_counts=2047)
    assert int(np.argmax(abs(np.fft.fft(result.iq)))) == expected_bin
    expected = 2047 * np.exp(2j * np.pi * offset * np.arange(512) / 1_024_000)
    np.testing.assert_array_equal(result.iq,
                                  np.rint(expected.real) + 1j * np.rint(expected.imag))
    assert result.bits.size == result.symbols.size == result.taps.size == 0
    assert result.reference["symbol_rate_hz"] is None


def test_le_int16_interleaving_left_shift_and_signed_extremes():
    logical = np.array([2047 - 2048j, -1 + 1j, 0j])
    packed = pack_tx_iq_le16(logical)
    assert packed == struct.pack("<hhhhhh", 32752, -32768, -16, 16, 0, 0)
    words = np.frombuffer(packed, dtype="<i2")
    assert np.all((words.astype(np.int32) & 15) == 0)
    recovered = (words.astype(np.int32) >> 4).reshape(-1, 2)
    np.testing.assert_array_equal(recovered[:, 0] + 1j * recovered[:, 1], logical)


@pytest.mark.parametrize("mode", ["tone", "BPSK", "QPSK", "16QAM"])
def test_maximum_requested_peak_has_no_clipping_or_low_bits(mode):
    result = make_tx_waveform(mode, sample_rate_hz=1_000_000,
                              symbol_count=128, seed=0, digital_peak_counts=2047)
    words = np.frombuffer(pack_tx_iq_le16(result.iq), dtype="<i2").reshape(-1, 2)
    assert np.max(np.abs(words.astype(np.int32))) == 32752
    assert np.all((words.astype(np.int32) & 15) == 0)
    np.testing.assert_array_equal(words[:, 0] + 1j * words[:, 1], result.storage_iq)


def test_generation_reproducibility_and_seed_changes_modulated_payload():
    first = make_tx_waveform("16QAM", sample_rate_hz=1_000_000, seed=44)
    second = make_tx_waveform("16QAM", sample_rate_hz=1_000_000, seed=44)
    other = make_tx_waveform("16QAM", sample_rate_hz=1_000_000, seed=45)
    np.testing.assert_array_equal(first.bits, second.bits)
    assert pack_tx_iq_le16(first.iq) == pack_tx_iq_le16(second.iq)
    assert first.reference == second.reference
    assert not np.array_equal(first.bits, other.bits)


@pytest.mark.parametrize("kwargs", [
    {"sample_rate_hz": 0}, {"sample_rate_hz": True}, {"sample_rate_hz": 1_000_000.0},
    {"sample_rate_hz": 2**100}, {"samples_per_symbol": 0},
    {"samples_per_symbol": 1.5}, {"samples_per_symbol": True},
    {"symbol_count": -1}, {"symbol_count": 1.5},
    {"symbol_count": MAX_SAMPLE_COUNT, "samples_per_symbol": 2},
    {"symbol_count": 1, "samples_per_symbol": 1},
    {"span_symbols": MAX_SAMPLE_COUNT}, {"span_symbols": 3, "samples_per_symbol": 3},
    {"seed": -1}, {"seed": 2**32}, {"seed": True}, {"seed": 1.5},
    {"digital_peak_counts": 0}, {"digital_peak_counts": 2048},
    {"digital_peak_counts": 32767}, {"digital_peak_counts": True}, {"digital_peak_counts": 2.5},
    {"offset_hz": np.nan}, {"offset_hz": np.inf}, {"offset_hz": 1e308},
    {"offset_hz": True}, {"offset_hz": "125000"},
    {"offset_hz": 1}, {"offset_hz": 500_000},
    {"offset_hz": 450_000},  # Coherent but theoretical RRC edge aliases.
    {"rolloff": -0.1}, {"rolloff": 1.1}, {"rolloff": np.nan},
])
def test_invalid_requests_rejected_before_generation(kwargs):
    arguments = {"sample_rate_hz": 1_000_000, "samples_per_symbol": 8,
                 "symbol_count": 125}
    arguments.update(kwargs)
    with pytest.raises(ValueError):
        make_tx_waveform("QPSK", **arguments)


@pytest.mark.parametrize("mode", ["QAM64", "", None, 1])
def test_invalid_modulation(mode):
    with pytest.raises(ValueError):
        make_tx_waveform(mode, sample_rate_hz=1_000_000)


@pytest.mark.parametrize("iq", [[], [[1, 2]], [np.nan], [np.inf], [2048],
                                      [-2049j], [1.5], [0.5j], [1e200]])
def test_packing_rejects_invalid_or_overflowing_codes(iq):
    with pytest.raises(ValueError):
        pack_tx_iq_le16(iq)


@pytest.mark.parametrize("symbols,taps,sps", [([], [1], 2), ([1], [], 2),
    ([1], [1, 1], 2), ([np.inf], [1], 2), ([1], [np.nan], 2),
    ([1], [1], MAX_SAMPLE_COUNT + 1), ([1e308], [1e308], 2)])
def test_circular_shape_rejects_invalid_parameters_and_overflow(symbols, taps, sps):
    with pytest.raises(ValueError):
        circular_shape_symbols(symbols, taps, sps)
