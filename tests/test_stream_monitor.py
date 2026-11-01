"""Independent checks of bounded retention, durable chunks and RX lifecycle."""

import json
from threading import Event

import numpy as np
import pytest

import rfsig.rx_monitor as finite
import rfsig.stream_monitor as streaming
from rfsig.rx_monitor import RxBlock
from rfsig.stream_monitor import StreamMonitor, load_archive_chunk, run_stream_monitor, verify_stream_archive


BASE, N, FS = 1000.0, 32, 32000
SETTINGS = {"sample_rate_hz": FS, "rx_rf_bandwidth_hz": 24000,
            "rx_lo_hz": 2400000000, "gain_control_mode": "slow_attack", "rx_port": "A_BALANCED"}


@pytest.fixture(autouse=True)
def fixed_session_clock(monkeypatch):
    monkeypatch.setattr(finite, "perf_counter", lambda: BASE)
    monkeypatch.setattr(streaming, "perf_counter", lambda: BASE)


def make_block(index, amplitude=None):
    amplitude = index + 1 if amplitude is None else amplitude
    samples = amplitude * np.exp(2j * np.pi * 3 * np.arange(N) / N)
    return RxBlock(samples, BASE + index + 0.1, BASE + index + 0.2, 10., 11.)


def new_monitor(path, **kwargs):
    return StreamMonitor(SETTINGS, path, fft_size=N, history_frames=4, chunk_frames=3,
                         source_kind="synthetic_test", **kwargs)


class Receiver:
    settings, fft_size = SETTINGS, N

    def __init__(self, fail_after=None, cleanup_fails=False):
        self.read_count, self.fail_after = 0, fail_after
        self.cleanup_fails = cleanup_fails
        self.cleanup_completed = False

    def __enter__(self):
        return self

    def read(self):
        if self.fail_after == self.read_count:
            raise OSError("injected RX disconnect")
        result = make_block(self.read_count)
        self.read_count += 1
        return result

    def __exit__(self, *_):
        if self.cleanup_fails:
            raise OSError("injected cleanup failure")
        self.cleanup_completed = True


def run(receiver, path, **kwargs):
    return run_stream_monitor(lambda: receiver, path, history_frames=4, chunk_frames=3,
                              interval_seconds=0, source_kind="synthetic_test", **kwargs)


def chunks(path):
    return [load_archive_chunk(p) for p in sorted(path.glob("chunk-*"))]


def test_longer_than_retained_history_keeps_all_archived_blocks(tmp_path):
    out = tmp_path / "session"
    receiver = Receiver()
    session = run(receiver, out, max_blocks=101)
    report, arrays = session.snapshot()
    assert report["received_block_count"] == 101
    assert report["frame_count"] == report["retained_block_count"] == 4
    assert report["max_history_observed"] == 4
    assert report["max_pending_observed"] == 3
    assert report["rolling_evicted_blocks"] == 97
    assert report["archive_chunk_count"] == 34
    assert report["archived_block_count"] == 101
    assert report["archive_finalized"] and report["receive_context_released"]
    assert report["state"] == "block_limit"
    assert not report["hardware_continuity_verified"] and not report["ai_connected"]
    np.testing.assert_array_equal(arrays["block_numbers"], [98, 99, 100, 101])
    archived = chunks(out)
    np.testing.assert_array_equal(np.concatenate([a["block_numbers"] for _, a in archived]), np.arange(1, 102))
    expected = np.stack([make_block(i).iq for i in range(101)])
    np.testing.assert_array_equal(np.concatenate([a["iq_frames"] for _, a in archived]), expected)
    # Independent direct DFT, without the production FFT/PSD helper.
    t = np.arange(N)
    window = (1 - np.cos(2 * np.pi * t / N)) / 2
    matrix = np.exp(-2j * np.pi * t[:, None] * t[None, :] / N)
    oracle = np.abs((expected * window) @ matrix.T) ** 2 / (FS * (window @ window))
    oracle = np.concatenate((oracle[:, N//2:], oracle[:, :N//2]), axis=1)
    actual = np.concatenate([a["psd_frames"] for _, a in archived])
    np.testing.assert_allclose(actual, oracle, atol=1e-24, rtol=1e-10)
    for meta, array in archived:
        assert meta["source_kind"] == "synthetic_test"
        assert meta["power_reference"] == pytest.approx(1)
        expected_ratio = 20 * np.log10(array["block_numbers"])
        np.testing.assert_allclose(meta["relative_db"], expected_ratio, atol=1e-12)


def test_stop_releases_receiver_and_flushes_last_partial_chunk(tmp_path):
    stop = Event()
    events = []
    def observe(snapshot):
        events.append(snapshot[0])
        if snapshot[0]["received_block_count"] == 8:
            stop.set()
    receiver = Receiver()
    session = run(receiver, tmp_path / "stop", stop_event=stop, on_snapshot=observe)
    assert receiver.read_count == 8 and receiver.cleanup_completed
    assert session.state == "stopped" and session.archived == 8
    assert [r["frame_count"] for r, _ in chunks(session.directory)] == [3, 3, 2]
    assert events[-1]["receive_context_released"]
    assert events[-1]["archive_finalized"]


def test_reopen_is_independent_and_never_overwrites_existing_session(tmp_path):
    first = run(Receiver(), tmp_path / "one", max_blocks=2)
    second = run(Receiver(), tmp_path / "two", max_blocks=4)
    assert first.received == 2 and second.received == 4
    before = (first.directory / "session.json").read_bytes()
    receiver = Receiver()
    with pytest.raises(FileExistsError):
        run(receiver, first.directory, max_blocks=1)
    assert receiver.cleanup_completed and receiver.read_count == 0
    assert (first.directory / "session.json").read_bytes() == before


def test_rx_disconnect_retains_accepted_data_and_error_state(tmp_path):
    receiver = Receiver(fail_after=5)
    session = run(receiver, tmp_path / "failure", max_blocks=10)
    assert session.state == "error" and "disconnect" in session.error
    assert session.received == session.archived == 5
    assert session.context_released and session.finalized
    assert sum(m["frame_count"] for m, _ in chunks(session.directory)) == 5


def test_cleanup_failure_is_not_reported_as_released(tmp_path):
    session = run(Receiver(cleanup_fails=True), tmp_path / "cleanup", max_blocks=2)
    assert session.state == "error" and "cleanup failure" in session.error
    assert not session.context_released
    assert session.archived == 2


def test_stop_already_requested_does_not_read(tmp_path):
    stop = Event()
    stop.set()
    receiver = Receiver()
    session = run(receiver, tmp_path / "empty", stop_event=stop)
    assert receiver.read_count == 0 and receiver.cleanup_completed
    assert session.state == "stopped" and session.finalized
    assert not list(session.directory.glob("chunk-*"))
    assert json.loads((session.directory / "session.json").read_text())["received_block_count"] == 0


def test_time_limit_checks_before_acquiring_another_block(tmp_path, monkeypatch):
    clock = iter([BASE, BASE + .5, BASE + 1.1])
    monkeypatch.setattr(streaming, "perf_counter", lambda: next(clock))
    receiver = Receiver()
    session = run(receiver, tmp_path / "time", max_duration_seconds=1)
    assert session.state == "time_limit" and session.received == 2
    assert receiver.cleanup_completed and session.finalized


def test_disk_quota_stops_before_read_and_flushes_every_accepted_block(tmp_path):
    receiver = Receiver()
    session = run(receiver, tmp_path / "quota", max_archive_bytes=145000, max_blocks=1000)
    assert session.state == "archive_limit"
    assert 0 < session.received < 1000
    assert session.archived == session.received == receiver.read_count
    assert session.finalized and session.context_released
    file_bytes = sum(p.stat().st_size for p in session.directory.rglob("*") if p.is_file())
    assert file_bytes <= session.max_archive_bytes


def test_hash_tampering_is_rejected(tmp_path):
    session = run(Receiver(), tmp_path / "tamper", max_blocks=2)
    path = session.directory / "chunk-000001" / "monitor.npz"
    path.write_bytes(path.read_bytes() + b"corruption")
    with pytest.raises(ValueError, match="hash mismatch"):
        load_archive_chunk(path.parent)


def test_metadata_count_and_sequence_mismatch_is_rejected(tmp_path):
    session = run(Receiver(), tmp_path / "tamper", max_blocks=2)
    path = session.directory / "chunk-000001" / "report.json"
    meta = json.loads(path.read_text())
    meta["last_block_number"] = 99
    path.write_text(json.dumps(meta))
    with pytest.raises(ValueError, match="numbering"):
        load_archive_chunk(path.parent)


def test_rolling_snapshot_does_not_alias_future_evidence(tmp_path):
    monitor = new_monitor(tmp_path / "isolation")
    samples = make_block(0)
    monitor.append(samples)
    meta, arrays = monitor.snapshot()
    arrays["iq_frames"][:] = 99
    meta["settings"]["rx_lo_hz"] = -1
    meta["bandwidths"][0]["bandwidth_hz"] = -1
    fresh, values = monitor.snapshot()
    np.testing.assert_array_equal(values["iq_frames"][0], samples.iq)
    assert fresh["settings"]["rx_lo_hz"] == SETTINGS["rx_lo_hz"]
    assert fresh["bandwidths"][0]["bandwidth_hz"] >= 0


def test_zero_frames_do_not_create_invalid_json_or_power_reference(tmp_path):
    monitor = new_monitor(tmp_path / "zero")
    for i in range(4):
        monitor.append(make_block(i, amplitude=0))
    monitor.flush()
    meta, _ = monitor.snapshot()
    assert meta["power_reference"] is None
    json.dumps(meta, allow_nan=False)
    for chunk_meta, _ in chunks(monitor.directory):
        assert chunk_meta["relative_db"] == [None] * chunk_meta["frame_count"]


@pytest.mark.parametrize("options", [
    {"history_frames": 0}, {"history_frames": True}, {"chunk_frames": -1},
    {"max_archive_bytes": 10}, {"max_archive_bytes": True},
    {"history_frames": 1000000}, {"source_kind": "real RF already verified"},
])
def test_invalid_storage_configuration_is_rejected_before_directory_creation(tmp_path, options):
    defaults = dict(fft_size=N, history_frames=4, chunk_frames=3, source_kind="synthetic_test")
    defaults.update(options)
    with pytest.raises(ValueError):
        StreamMonitor(SETTINGS, tmp_path / "invalid", **defaults)
    assert not (tmp_path / "invalid").exists()


@pytest.mark.parametrize("options", [
    {"interval_seconds": -1}, {"interval_seconds": True},
    {"max_duration_seconds": 0}, {"max_duration_seconds": float("nan")},
    {"max_blocks": 0}, {"max_blocks": True},
])
def test_invalid_run_options_do_not_connect(tmp_path, options):
    def forbidden():
        raise AssertionError("Do not open RX for invalid parameters")
    with pytest.raises(ValueError):
        run_stream_monitor(forbidden, tmp_path / "invalid", **options)


def test_storage_failure_preserves_partial_files_and_reports_unarchived_data(tmp_path, monkeypatch):
    original_open = type(tmp_path).open
    def fail_npz(path, mode='r', *args, **kwargs):
        if path.name == "monitor.npz" and mode == "xb":
            raise OSError("injected disk full")
        return original_open(path, mode, *args, **kwargs)
    monkeypatch.setattr(type(tmp_path), "open", fail_npz)
    receiver = Receiver()
    session = run(receiver, tmp_path / "disk-full", max_blocks=5)
    assert session.state == "error" and "disk full" in session.error
    assert session.received == 3 and session.archived == 0
    assert len(session.pending) == 3 and not session.finalized
    assert receiver.cleanup_completed and session.context_released
    saved = json.loads((session.directory / "session.json").read_text())
    assert saved["storage_error"] and not saved["archive_finalized"]


def test_independent_archive_verifier_recomputes_every_frame(tmp_path):
    session = run(Receiver(), tmp_path / "verified", max_blocks=19)
    result = verify_stream_archive(session.directory)
    assert result["verified_blocks"] == result["received_blocks"] == 19
    assert result["unique_block_count"] == 19
    assert result["archive_complete"] and result["receive_context_released"]
    assert result["all_saved_blocks_independently_recomputed"]
    assert result["max_roi_edge_error_hz"] < 1e-6


def test_verifier_handles_zero_reference_then_first_positive_in_later_chunk(tmp_path):
    class ZeroFirst(Receiver):
        def read(self):
            item = make_block(self.read_count, amplitude=0 if self.read_count < 5 else 2)
            self.read_count += 1
            return item
    session = run(ZeroFirst(), tmp_path / "zero-first", max_blocks=8)
    assert verify_stream_archive(session.directory)["archive_complete"]


@pytest.mark.parametrize("corruption", ["missing_chunk", "journal", "configuration", "power", "finalized_count"])
def test_archive_verifier_rejects_missing_or_inconsistent_evidence(tmp_path, corruption):
    session = run(Receiver(), tmp_path / "corruption", max_blocks=4)
    root = session.directory
    if corruption == "missing_chunk":
        (root / "chunk-000002").rename(root / "missing-chunk")
    elif corruption == "journal":
        path = root / "chunks.jsonl"
        records = path.read_text().splitlines()
        path.write_text(records[0] + '\n')
    elif corruption == "finalized_count":
        path = root / "session.json"
        meta = json.loads(path.read_text())
        meta["received_block_count"] += 1
        path.write_text(json.dumps(meta))
    else:
        path = root / "chunk-000001" / "report.json"
        meta = json.loads(path.read_text())
        if corruption == "configuration":
            meta["settings"]["rx_lo_hz"] += 1000
        else:
            meta["relative_db"][0] = 100
        path.write_text(json.dumps(meta))
    with pytest.raises((ValueError, AssertionError)):
        verify_stream_archive(root)
