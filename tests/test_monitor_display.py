"""Replay pause/reset/end and provenance; no hardware or GUI."""

import hashlib
import json

import numpy as np
import pytest

import rfsig.rx_monitor as finite
from rfsig.rx_monitor import RxBlock
from rfsig.stream_monitor import StreamMonitor
from rfsig.monitor_display import ArchiveReplay, save_display_snapshot


@pytest.fixture
def archive(tmp_path, monkeypatch):
    monkeypatch.setattr(finite, "perf_counter", lambda: 100.)
    settings = {"sample_rate_hz": 64000, "rx_rf_bandwidth_hz": 48000,
                "rx_lo_hz": 2400000000, "gain_control_mode": "slow_attack", "rx_port": "A_BALANCED"}
    monitor = StreamMonitor(settings, tmp_path / "archive", fft_size=64, history_frames=4,
                            chunk_frames=3, source_kind="synthetic_test")
    for i in range(11):
        iq = (i+1) * np.exp(2j*np.pi*5*np.arange(64)/64)
        monitor.append(RxBlock(iq, 100+i+.1, 100+i+.2, 10., 11.))
    monitor.flush()
    monitor.state, monitor.context_released, monitor.finalized = "stopped", True, True
    monitor.write_summary()
    return monitor.directory


def test_replay_pause_resume_end_preserves_source_and_every_block(archive):
    replay = ArchiveReplay(archive, history_frames=4)
    assert replay.snapshot()[0]["playback_position"] == 0
    assert replay.advance()[0]["playback_position"] == 0
    replay.start()
    for _ in range(5):
        snapshot = replay.advance()
    assert replay.position == 5
    assert snapshot[0]["display_mode"] == "saved_archive"
    assert snapshot[0]["source_kind"] == "synthetic_test"
    np.testing.assert_array_equal(snapshot[1]["block_numbers"], [2, 3, 4, 5])
    replay.pause()
    frozen = replay.advance()
    np.testing.assert_array_equal(frozen[1]["iq_frames"], snapshot[1]["iq_frames"])
    assert replay.position == 5
    replay.start()
    while replay.state == "playing":
        snapshot = replay.advance()
    assert replay.position == 11 and replay.state == "finished"
    replay.start()
    assert replay.state == "finished"
    np.testing.assert_array_equal(snapshot[1]["block_numbers"], [8, 9, 10, 11])
    replay.reset()
    assert replay.position == 0 and replay.state == "paused"
    assert replay.snapshot()[1]["iq_frames"].shape == (0, 64)
    replay.start()
    assert replay.advance()[1]["block_numbers"].tolist() == [1]


def test_replay_and_export_do_not_modify_source_or_claim_full_session(archive, tmp_path):
    before = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in archive.rglob('*') if path.is_file()}
    replay = ArchiveReplay(archive, history_frames=4)
    replay.start()
    for _ in range(6):
        snapshot = replay.advance()
    target = save_display_snapshot(snapshot, tmp_path / "export", display_mode="saved_archive", display_updates=6)
    meta = json.loads((target / "snapshot.json").read_text(encoding="utf-8"))
    assert meta["display_mode"] == "saved_archive"
    assert meta["export_kind"] == "retained_window_only_not_entire_session"
    assert meta["frame_count"] == 4 and meta["playback_position"] == 6
    assert meta["received_block_count"] == 11
    assert not meta["gui_interaction_verified"]
    assert hashlib.sha256((target / "snapshot.npz").read_bytes()).hexdigest() == meta["snapshot_arrays_sha256"]
    for name, digest in before.items():
        from pathlib import Path
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest


def test_caller_mutation_cannot_change_replay_history(archive):
    replay = ArchiveReplay(archive)
    replay.start()
    meta, arrays = replay.advance()
    original = arrays["iq_frames"].copy()
    meta["bandwidths"][0]["bandwidth_hz"] = -9
    arrays["iq_frames"][:] = 99
    meta2, arrays2 = replay.snapshot()
    np.testing.assert_array_equal(original, arrays2["iq_frames"])
    assert meta2["bandwidths"][0]["bandwidth_hz"] > 0


def test_snapshot_export_rejects_empty_and_overwrite(archive, tmp_path):
    replay = ArchiveReplay(archive)
    with pytest.raises(ValueError, match="No displayed"):
        save_display_snapshot(replay.snapshot(), tmp_path / "empty", display_mode="saved_archive")
    assert not (tmp_path / "empty").exists()
    replay.start()
    snapshot = replay.advance()
    target = save_display_snapshot(snapshot, tmp_path / "one", display_mode="saved_archive")
    with pytest.raises(FileExistsError):
        save_display_snapshot(snapshot, target, display_mode="saved_archive")


def test_missing_or_modified_archive_is_not_silently_replayed(archive):
    payload = archive / "chunk-000002" / "monitor.npz"
    payload.write_bytes(payload.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="hash mismatch"):
        ArchiveReplay(archive)
