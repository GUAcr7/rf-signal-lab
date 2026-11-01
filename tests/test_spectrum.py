import numpy as np
import pytest

from rfsig.spectrum import power_periodogram, welch_power_spectrum


FS = 30_720_000
N = 1024


@pytest.mark.parametrize("window", ["rectangular", "hann_periodic"])
@pytest.mark.parametrize("frequency", [960_000, -960_000])
def test_known_tone_frequency_and_total_power(window, frequency):
    # Construct directly from the theoretical phase, independent of tone.py.
    iq = 0.5 * np.exp(2j * np.pi * frequency * np.arange(N) / FS)
    result = power_periodogram(iq, FS, window)
    assert result.frequency_hz[np.argmax(result.psd)] == frequency
    assert result.bin_width_hz == 30_000
    assert result.frequency_hz[0] == -FS / 2
    assert result.frequency_hz[-1] == FS / 2 - 30_000
    assert np.all(np.diff(result.frequency_hz) == 30_000)
    assert result.bin_power.sum() == pytest.approx(0.25, abs=1e-14)
    assert result.time_mean_power == pytest.approx(0.25, abs=1e-14)


def test_periodic_hann_distributes_aligned_tone_power_over_three_bins():
    iq = 0.5 * np.exp(2j * np.pi * 32 * np.arange(N) / N)
    result = power_periodogram(iq, FS)
    peak = int(np.argmax(result.psd))
    np.testing.assert_allclose(result.bin_power[peak-1:peak+2],
                               np.array([1/6, 2/3, 1/6]) * 0.25, atol=1e-14)
    assert np.delete(result.bin_power, [peak-1, peak, peak+1]).sum() < 1e-24


def test_direct_fourier_sum_is_an_independent_small_vector_reference():
    iq = np.array([1+2j, -3+1j, 0j, 2-1j, 1j, -1-2j, 4+0j, 2j])
    count = len(iq)
    # Direct DFT matrix, not another call to the FFT implementation.
    kernel = np.exp(-2j*np.pi*np.arange(count)[:, None]*np.arange(count)[None, :]/count)
    expected_bin_power = np.abs(kernel @ iq)**2 / count**2
    expected_psd = np.concatenate((expected_bin_power[4:], expected_bin_power[:4])) / 1000
    result = power_periodogram(iq, 8000, "rectangular")
    np.testing.assert_allclose(result.psd, expected_psd, atol=1e-16)
    assert result.bin_power.sum() == pytest.approx(np.mean(np.abs(iq)**2))


@pytest.mark.parametrize("window", ["rectangular", "hann_periodic"])
def test_amplitude_doubling_quadruples_power(window):
    iq = np.random.default_rng(15).normal(size=127) + 1j*np.random.default_rng(16).normal(size=127)
    original = power_periodogram(iq, 1e6, window)
    doubled = power_periodogram(2*iq, 1e6, window)
    np.testing.assert_allclose(doubled.psd, 4*original.psd)
    assert 10*np.log10(doubled.bin_power.sum()/original.bin_power.sum()) == pytest.approx(6.020599913279624)


def test_weighted_parseval_for_nonstationary_signal_and_preserved_input():
    iq = np.arange(17) + 1j*np.arange(17)[::-1]
    original = iq.copy()
    weights = 0.5-0.5*np.cos(2*np.pi*np.arange(17)/17)
    expected = np.sum(np.abs(iq)**2*weights**2)/np.sum(weights**2)
    result = power_periodogram(iq, 1e6)
    assert result.bin_power.sum() == pytest.approx(expected, rel=1e-14)
    assert result.window_weighted_mean_power == pytest.approx(expected)
    assert result.time_mean_power == pytest.approx(np.mean(np.abs(iq)**2))
    assert not np.isclose(result.time_mean_power, expected)
    np.testing.assert_array_equal(iq, original)


def test_complex_positive_and_negative_tones_are_not_folded_or_doubled():
    n = np.arange(64)
    iq = 0.5*np.exp(2j*np.pi*5*n/64) + 0.25*np.exp(-2j*np.pi*9*n/64)
    result = power_periodogram(iq, 64_000, "rectangular")
    assert result.bin_power[result.frequency_hz == 5000][0] == pytest.approx(0.25)
    assert result.bin_power[result.frequency_hz == -9000][0] == pytest.approx(0.0625)
    assert result.bin_power.sum() == pytest.approx(0.3125)


@pytest.mark.parametrize("count,fs", [(15, 15000), (16, 32000), (1024, FS)])
def test_frequency_axis_handles_odd_length_and_sample_rate(count, fs):
    iq = np.exp(2j*np.pi*2*np.arange(count)/count)
    result = power_periodogram(iq, fs, "rectangular")
    assert result.frequency_hz[np.argmax(result.psd)] == pytest.approx(2*fs/count)
    np.testing.assert_allclose(np.diff(result.frequency_hz), fs/count)


def test_dc_is_retained_and_zero_input_has_no_power():
    result = power_periodogram(np.ones(16, dtype=complex)*(3+4j), 16000, "rectangular")
    assert result.frequency_hz[np.argmax(result.psd)] == 0
    assert result.bin_power.sum() == pytest.approx(25)
    zero = power_periodogram(np.zeros(16, dtype=complex), 16000)
    np.testing.assert_array_equal(zero.psd, np.zeros(16))
    assert zero.time_mean_power == 0


@pytest.mark.parametrize("iq,fs,window", [
    ([], 1000, "rectangular"),
    ([1, 2, 3], 1000, "rectangular"),
    (np.zeros((4, 2)), 1000, "rectangular"),
    ([1, 2, 3, np.nan], 1000, "rectangular"),
    ([1, 2, 3, np.inf], 1000, "rectangular"),
    ([1j]*4, 0, "rectangular"),
    ([1j]*4, np.nan, "rectangular"),
    ([1j]*4, 1000, "unknown"),
    (["a"]*4, 1000, "rectangular"),
])
def test_rejects_invalid_spectrum_inputs(iq, fs, window):
    with pytest.raises(ValueError):
        power_periodogram(iq, fs, window)


# --- Welch averaging: the doubling bug that this suite must keep out ---------
#
# The original OBW script multiplied every bin except DC and the last by 2.0,
# which is the real-signal one-sided convention. For complex I/Q the spectrum is
# not conjugate-symmetric, so that inflates essentially all bins and breaks both
# total power and any band edge landing on the two undoubled bins.

@pytest.mark.parametrize("window", ["rectangular", "hann_periodic"])
def test_welch_conserves_power_for_complex_noise(window):
    rng = np.random.default_rng(20261017)
    iq = (rng.standard_normal(16384) + 1j * rng.standard_normal(16384)) / np.sqrt(2)
    result = welch_power_spectrum(iq, FS, 1024, 0.5, window)
    total = float(result.bin_power.sum())
    # Two-sided, complex: sum(psd)*df must equal the window-weighted mean power,
    # not twice it.
    assert total == pytest.approx(result.window_weighted_mean_power, rel=1e-10)


@pytest.mark.parametrize("frequency", [960_000, -960_000])
def test_welch_keeps_a_complex_tone_on_one_side_only(frequency):
    iq = 0.75 * np.exp(2j * np.pi * frequency * np.arange(16384) / FS)
    result = welch_power_spectrum(iq, FS, 1024, 0.5)
    peak = result.frequency_hz[int(np.argmax(result.psd))]
    assert peak == frequency
    # A pure tone's power must come back as 0.75**2, not twice that.
    assert float(result.bin_power.sum()) == pytest.approx(0.5625, rel=1e-9)


def test_welch_with_one_segment_equals_the_plain_periodogram():
    rng = np.random.default_rng(5)
    iq = rng.standard_normal(1024) + 1j * rng.standard_normal(1024)
    welch = welch_power_spectrum(iq, FS, 1024, 0.0)
    plain = power_periodogram(iq, FS)
    np.testing.assert_allclose(welch.psd, plain.psd, rtol=1e-12, atol=0)
    assert welch.bin_width_hz == plain.bin_width_hz


def test_welch_reports_covered_power_not_the_whole_input():
    # 2600 samples with nperseg=1000 and 50% overlap give 4 segments ending at
    # sample 2500, so 100 samples are never analysed. The reported mean power
    # must come from the covered span only.
    rng = np.random.default_rng(11)
    iq = (rng.standard_normal(2600) + 1j * rng.standard_normal(2600)) / np.sqrt(2)
    result = welch_power_spectrum(iq, FS, 1000, 0.5)
    step = 500
    segments = 1 + (2600 - 1000) // step
    assert segments == 4
    covered = iq[:(segments - 1) * step + 1000]
    assert covered.size == 2500
    assert result.time_mean_power == pytest.approx(float(np.mean(np.abs(covered) ** 2)), rel=1e-12)
    assert result.time_mean_power != pytest.approx(float(np.mean(np.abs(iq) ** 2)), rel=1e-6)


@pytest.mark.parametrize("kwargs", [
    {"nperseg": 2}, {"nperseg": 8, "overlap": 1.0}, {"nperseg": 8, "overlap": -0.1},
    {"nperseg": 8, "overlap": np.nan}, {"nperseg": 8, "window": "blackman"},
    {"nperseg": True}, {"nperseg": 99999},
])
def test_welch_rejects_invalid_options(kwargs):
    iq = np.ones(64, dtype=complex)
    options = {"nperseg": 32}
    options.update(kwargs)
    with pytest.raises(ValueError):
        welch_power_spectrum(iq, 1e6, **options)
