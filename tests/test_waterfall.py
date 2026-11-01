import numpy as np
import pytest

from rfsig.waterfall import WaterfallHistory, waterfall_periodogram


def test_frequency_changes_appear_in_correct_time_rows_and_keep_power():
    n = np.arange(32)
    iq = np.concatenate([0.5*np.exp(-2j*np.pi*4*n/32),
                         0.5*np.exp(2j*np.pi*8*n/32),
                         0.5*np.exp(2j*np.pi*12*n/32)])
    result = waterfall_periodogram(iq, 32_000, fft_size=32, hop_samples=32)
    peaks = result.frequency_hz[np.argmax(result.psd, axis=1)]
    np.testing.assert_array_equal(peaks, [-4000, 8000, 12000])
    np.testing.assert_allclose(result.time_seconds, [15.5, 47.5, 79.5]/np.array(32_000))
    np.testing.assert_allclose(result.psd.sum(axis=1)*1000, 0.25, atol=1e-14)
    assert result.covered_samples == 96
    assert result.trailing_samples == 0


def test_overlap_does_not_duplicate_time_or_invent_tail_samples():
    result = waterfall_periodogram(np.ones(23, dtype=complex), 8_000,
                                   fft_size=8, hop_samples=4, window="rectangular")
    np.testing.assert_array_equal(result.frame_start_samples, [0, 4, 8, 12])
    np.testing.assert_allclose(result.time_seconds, np.array([3.5, 7.5, 11.5, 15.5])/8000)
    assert result.psd.shape == (4, 8)
    assert result.covered_samples == 20
    assert result.trailing_samples == 3
    np.testing.assert_allclose(result.psd.sum(axis=1)*1000, 1)


def test_two_rows_against_direct_dft_on_distinct_short_vectors():
    iq = np.array([1+2j, 3-1j, 2j, -2, 4j, 1-1j, -1+3j, 2+2j])
    n = np.arange(4)
    kernel = np.exp(-2j*np.pi*n[:, None]*n[None, :]/4)
    expected = []
    for frame in (iq[:4], iq[4:]):
        unshifted = np.abs(kernel @ frame)**2/(4000*4)
        expected.append(np.concatenate([unshifted[2:], unshifted[:2]]))
    result = waterfall_periodogram(iq, 4000, 4, 4, "rectangular")
    np.testing.assert_allclose(result.psd, expected, atol=1e-17)


def test_crossing_a_switch_boundary_contains_both_tones():
    iq = np.concatenate([np.ones(8, dtype=complex), (-1.)**np.arange(8)])
    result = waterfall_periodogram(iq, 8000, 8, 4, "rectangular")
    # Middle frame has a four-sample DC part followed by a Nyquist tone.
    assert result.psd[1, result.frequency_hz == 0][0] > 0
    assert result.psd[1, result.frequency_hz == -4000][0] > 0
    np.testing.assert_allclose(result.psd.sum(axis=1)*1000, 1)


def test_zero_frames_remain_zero_and_input_is_preserved():
    iq = np.zeros(17, dtype=complex)
    before = iq.copy()
    result = waterfall_periodogram(iq, 10_000, 5, 3)
    assert result.psd.shape == (5, 5)
    np.testing.assert_array_equal(result.psd, np.zeros((5, 5)))
    np.testing.assert_array_equal(iq, before)


@pytest.mark.parametrize("kwargs", [
    {"fft_size": 3}, {"fft_size": 4.5}, {"fft_size": True},
    {"hop_samples": 0}, {"hop_samples": 17}, {"hop_samples": False},
    {"sample_rate_hz": 0}, {"window": "bad"},
])
def test_rejects_invalid_framing(kwargs):
    settings = dict(sample_rate_hz=16000, fft_size=16, hop_samples=8)
    settings.update(kwargs)
    with pytest.raises(ValueError):
        waterfall_periodogram(np.zeros(32, dtype=complex), **settings)


@pytest.mark.parametrize("iq", [np.zeros(15), np.zeros((16, 2)), np.array(["a"]*16),
                                  np.concatenate([np.zeros(16), [np.nan]])])
def test_rejects_invalid_data_including_nonfinite_unused_tail(iq):
    with pytest.raises(ValueError):
        waterfall_periodogram(iq, 16000, fft_size=16)


def test_bounded_history_keeps_latest_rows_and_correct_eviction_count():
    history = WaterfallHistory([-2000, -1000, 0, 1000], max_rows=3)
    for i in range(7):
        history.append(np.full(4, i), i/10)
    times, frequencies, psd = history.snapshot()
    np.testing.assert_allclose(times, [0.4, 0.5, 0.6])
    np.testing.assert_array_equal(psd, np.array([[4]*4, [5]*4, [6]*4]))
    np.testing.assert_array_equal(frequencies, [-2000, -1000, 0, 1000])
    assert history.rows_received == 7
    assert history.rows_evicted == 4


def test_history_does_not_alias_input_or_snapshot_arrays_and_can_reset():
    frequencies = np.array([-2., -1., 0., 1.])
    row = np.array([1., 2., 3., 4.])
    history = WaterfallHistory(frequencies, max_rows=1)
    history.append(row, 1)
    row[:] = 9
    frequencies[:] = 10
    times, axis, psd = history.snapshot()
    psd[:] = 5
    axis[:] = 20
    times[:] = 100
    np.testing.assert_array_equal(history.snapshot()[2], [[1, 2, 3, 4]])
    np.testing.assert_array_equal(history.snapshot()[1], [-2, -1, 0, 1])
    history.reset()
    assert history.snapshot()[2].shape == (0, 4)
    assert history.rows_received == history.rows_evicted == 0
    history.append(np.zeros(4), 0)
    assert history.snapshot()[0][0] == 0


@pytest.mark.parametrize("row,time", [
    ([1]*3, 2), ([1, -1, 1, 1], 2), ([np.nan]*4, 2),
    ([1j]*4, 2), ([1]*4, np.inf), ([1]*4, 1), ([1]*4, 0),
])
def test_invalid_history_append_does_not_change_existing_state(row, time):
    history = WaterfallHistory([-2, -1, 0, 1], 2)
    history.append(np.ones(4), 1)
    with pytest.raises(ValueError):
        history.append(row, time)
    assert history.rows_received == 1
    assert history.rows_evicted == 0
    np.testing.assert_array_equal(history.snapshot()[0], [1])


@pytest.mark.parametrize("axis,rows", [
    ([-2, -1, 0, 1], 0), ([-2, -1, 0, 1], True),
    ([0, 0, 1, 2], 2), ([0, 1, 2, np.nan], 2), ([[0, 1, 2, 3]], 2),
])
def test_rejects_invalid_history_configuration(axis, rows):
    with pytest.raises(ValueError):
        WaterfallHistory(axis, rows)
