import numpy as np
import pytest

from rfsig.tone import complex_tone


FS = 30_720_000
N = 1024


def _peak_bin(iq):
    return int(np.argmax(np.abs(np.fft.fft(iq))))


def test_known_positive_tone_has_expected_amplitude_and_fft_bin():
    iq = complex_tone(FS, N, 960_000, amplitude=0.5)

    assert iq.shape == (N,)
    assert iq.dtype == np.complex128
    np.testing.assert_allclose(np.abs(iq), 0.5, rtol=0, atol=1e-12)
    np.testing.assert_allclose(iq[0], 0.5 + 0j, rtol=0, atol=1e-12)
    assert _peak_bin(iq) == 32
    np.testing.assert_allclose(np.abs(np.fft.fft(iq)[32]), 512, rtol=0, atol=1e-9)


def test_changing_tone_frequency_moves_peak_by_known_bins():
    first = complex_tone(FS, N, 960_000)
    second = complex_tone(FS, N, 1_920_000)

    assert _peak_bin(first) == 32
    assert _peak_bin(second) == 64


def test_negative_tone_appears_on_negative_frequency_side():
    iq = complex_tone(FS, N, -960_000)
    peak_hz = np.fft.fftfreq(N, 1 / FS)[_peak_bin(iq)]

    assert peak_hz == -960_000


@pytest.mark.parametrize(
    "kwargs",
    [
        {"sample_rate_hz": 0},
        {"sample_count": 0},
        {"sample_count": 1.5},
        {"frequency_offset_hz": FS / 2},
        {"amplitude": -0.1},
    ],
)
def test_rejects_invalid_tone_settings(kwargs):
    settings = dict(sample_rate_hz=FS, sample_count=N, frequency_offset_hz=960_000)
    settings.update(kwargs)
    with pytest.raises(ValueError):
        complex_tone(**settings)
