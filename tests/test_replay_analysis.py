"""Finite replay behavior, independent DSP checks and preserved evidence."""

import json

import numpy as np
import pytest

from rfsig.replay_analysis import OfflineReplay, save_replay_snapshot
from rfsig.waterfall import waterfall_periodogram


def make_replay(iq=None, **options):
    if iq is None:
        iq = 0.5*np.exp(2j*np.pi*128*np.arange(32)/1024)
    return OfflineReplay(iq, 1024, 8, 4, (-256, 256), 0.25, **options)


def test_pause_resume_retains_cursor_and_sample_time():
    replay = make_replay()
    assert replay.advance() is None
    replay.start()
    first = replay.advance()
    assert first.number == 0 and first.start_sample == 0
    assert first.time_seconds == 3.5/1024
    replay.pause()
    for _ in range(3):
        assert replay.advance() is None
    assert replay.next_frame == 1 and replay.history.rows_received == 1
    replay.start()
    second = replay.advance()
    assert second.start_sample == 4 and second.time_seconds == 7.5/1024
    assert second.mean_power == pytest.approx(0.25)
    assert second.relative_db == pytest.approx(0)


def test_finished_does_not_loop_or_append_even_after_start():
    replay = make_replay()
    replay.start()
    frames = [replay.advance() for _ in range(7)]
    assert [x.start_sample for x in frames] == list(range(0, 25, 4))
    assert replay.state == "finished"
    replay.start()
    assert replay.advance() is None and replay.history.rows_received == 7
    replay.pause()
    assert replay.state == "finished"


def test_reset_clears_state_and_restarts_exact_first_frame():
    replay = make_replay(max_rows=2)
    replay.start()
    first = replay.advance()
    replay.advance()
    replay.advance()
    assert replay.history.rows_evicted == 1
    replay.reset()
    assert replay.latest is None and replay.next_frame == 0 and replay.state == "paused"
    assert replay.history.rows_received == replay.history.rows_evicted == 0
    assert replay.history.snapshot()[2].shape == (0, 8)
    replay.start()
    again = replay.advance()
    np.testing.assert_array_equal(first.iq, again.iq)
    np.testing.assert_array_equal(first.spectrum.psd, again.spectrum.psd)
    assert first.bandwidth == again.bandwidth


def test_complete_frames_match_batch_reference_with_bounded_history():
    replay = make_replay(max_rows=3)
    expected = waterfall_periodogram(replay.iq, 1024, 8, 4)
    replay.start()
    frames = [replay.advance() for _ in range(replay.frame_count)]
    np.testing.assert_array_equal(np.stack([f.spectrum.psd for f in frames]), expected.psd)
    np.testing.assert_array_equal([f.time_seconds for f in frames], expected.time_seconds)
    np.testing.assert_array_equal(replay.history.snapshot()[2], expected.psd[-3:])
    assert replay.history.rows_evicted == 4
    for frame in frames:
        assert frame.spectrum.frequency_hz[np.argmax(frame.spectrum.psd)] == 128


def test_input_copied_and_trailing_partial_window_never_padded():
    iq = np.arange(11, dtype=np.int16)
    replay = make_replay(iq)
    iq[:] = 0
    replay.start()
    frame = replay.advance()
    np.testing.assert_array_equal(frame.iq.real, np.arange(8))
    assert replay.frame_count == 1 and replay.trailing_samples == 3
    assert replay.state == "finished"


def test_zero_power_returns_invalid_band_and_persists_strict_json(tmp_path):
    replay = make_replay(np.zeros(8))
    replay.start()
    frame = replay.advance()
    assert frame.mean_power == 0 and frame.relative_db == -np.inf
    assert frame.bandwidth.status == "no_effective_power"
    target = save_replay_snapshot(replay, tmp_path/"zero", {"kind": "synthetic"})
    report = json.loads((target/"report.json").read_text(encoding="utf-8"))
    assert report["relative_db"] is None and report["relative_db_status"] == "zero_power"
    assert report["bandwidth"]["bandwidth_hz"] is None
    assert report["gui_interaction_verified"] is False


def test_snapshot_matches_frame_and_rejects_overwrite(tmp_path):
    replay = make_replay()
    replay.start()
    frame = replay.advance()
    target = save_replay_snapshot(replay, tmp_path/"snapshot", {"kind": "saved_real", "label": None})
    with np.load(target/"analysis.npz", allow_pickle=False) as arrays:
        np.testing.assert_array_equal(arrays["iq"], frame.iq)
        np.testing.assert_array_equal(arrays["psd"], frame.spectrum.psd)
        np.testing.assert_array_equal(arrays["history_psd"], frame.spectrum.psd[np.newaxis, :])
    report = json.loads((target/"report.json").read_text(encoding="utf-8"))
    assert report["power_reference"] == 0.25
    assert not report["hardware_contacted"] and not report["target_detection_verified"]
    with pytest.raises(FileExistsError):
        save_replay_snapshot(replay, target, {})


def test_save_without_frame_creates_nothing(tmp_path):
    with pytest.raises(ValueError, match="No analyzed"):
        save_replay_snapshot(make_replay(), tmp_path/"empty", {})
    assert not (tmp_path/"empty").exists()


@pytest.mark.parametrize("iq", [[], np.zeros(7), np.zeros((8, 1)), [1]*7+[np.nan], ["a"]*8])
def test_invalid_source(iq):
    with pytest.raises(ValueError):
        make_replay(iq)


@pytest.mark.parametrize("name,value", [("sample_rate_hz", 0), ("sample_rate_hz", True),
                                      ("power_reference", 0), ("power_reference", np.inf),
                                      ("fft_size", True), ("fft_size", 8.5),
                                      ("hop_samples", 9), ("hop_samples", 0)])
def test_invalid_configuration(name, value):
    options = dict(sample_rate_hz=1024, fft_size=8, hop_samples=4,
                   analysis_band_hz=(-256, 256), power_reference=0.25)
    options[name] = value
    with pytest.raises(ValueError):
        OfflineReplay(np.ones(32), **options)
