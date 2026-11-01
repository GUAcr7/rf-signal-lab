import numpy as np
import pytest

from rfsig.sampling import sample_cosine


def test_time_grid_has_64_samples_without_the_4ms_endpoint() -> None:
    times, samples = sample_cosine(1_000, 16_000, 64)
    assert times.shape == samples.shape == (64,)
    assert times[0] == 0
    assert times[-1] == pytest.approx(0.0039375, abs=1e-15)
    np.testing.assert_allclose(np.diff(times), 0.0000625, rtol=0, atol=1e-15)


def test_quarter_cycle_values_match_hand_calculation() -> None:
    _, samples = sample_cosine(1_000, 16_000, 64)
    # cos at 0, 90, 180, 270 and 360 degrees; independent expected values.
    np.testing.assert_allclose(samples[[0, 4, 8, 12, 16]], [1, 0, -1, 0, 1],
                               rtol=0, atol=1e-12)


def test_waveform_repeats_every_16_samples() -> None:
    _, samples = sample_cosine(1_000, 16_000, 64)
    np.testing.assert_allclose(samples[16:], samples[:-16], rtol=0, atol=1e-12)


def test_amplitude_and_mean_square_for_complete_cycles() -> None:
    _, samples = sample_cosine(1_000, 16_000, 64, amplitude=2)
    assert samples.max() == pytest.approx(2)
    assert samples.min() == pytest.approx(-2)
    # A cosine over complete cycles has mean 0 and mean square A**2 / 2.
    assert np.mean(samples) == pytest.approx(0, abs=1e-12)
    assert np.mean(samples**2) == pytest.approx(2, abs=1e-12)


@pytest.mark.parametrize("frequency,rate,count,amplitude", [
    (1_000, 0, 64, 1), (1_000, 16_000, 0, 1),
    (1_000, 16_000, 2.5, 1), (float("nan"), 16_000, 64, 1),
    (1_000, 16_000, 64, -1),
])
def test_rejects_invalid_parameters(frequency, rate, count, amplitude) -> None:
    with pytest.raises(ValueError):
        sample_cosine(frequency, rate, count, amplitude)
