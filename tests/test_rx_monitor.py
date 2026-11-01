"""Offline RX-monitor evidence and lifecycle checks; no device or GUI imports."""

import builtins
import hashlib
import json
from threading import Event
from types import SimpleNamespace

import numpy as np
import pytest

import rfsig.rx_monitor as monitor
from rfsig.rx_monitor import (
    MonitorSession,
    P201Receiver,
    RxBlock,
    run_monitor_session,
    save_monitor_snapshot,
)


BASE = 1000.0
FS = 64_000
N = 64
SETTINGS = {
    "sample_rate_hz": FS,
    "rx_rf_bandwidth_hz": 48_000,
    "rx_lo_hz": 2_400_000_000,
    "gain_control_mode": "slow_attack",
    "rx_port": "A_BALANCED",
}


@pytest.fixture(autouse=True)
def deterministic_host_clock_and_no_optional_device_imports(monkeypatch):
    monkeypatch.setattr(monitor, "perf_counter", lambda: BASE)
    original_import = builtins.__import__

    def offline_import(name, *args, **kwargs):
        if name.split(".", 1)[0] in {"adi", "iio", "tkinter", "matplotlib"}:
            raise AssertionError(f"Offline monitor tests must not import {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", offline_import)


def tone(amplitude=2, bin_index=5, size=N):
    # Independent phase equation, without the project's tone/spectrum helpers.
    return amplitude * np.exp(2j * np.pi * bin_index * np.arange(size) / size)


def block(iq, start=0.25, end=0.5, before=10.0, after=10.0):
    return RxBlock(np.asarray(iq), BASE + start, BASE + end, before, after)


def new_session(frame_limit=10, fft_size=N, **settings):
    return MonitorSession({**SETTINGS, **settings}, frame_limit, fft_size)


def direct_hann_psd(iq, sample_rate):
    """Small direct DFT oracle, independent of np.fft and production helpers."""
    size = len(iq)
    samples = np.arange(size)
    window = (1 - np.cos(2 * np.pi * samples / size)) / 2
    dft = np.exp(-2j * np.pi * samples[:, None] * samples[None, :] / size)
    raw = np.abs(dft @ (iq * window)) ** 2 / (sample_rate * np.dot(window, window))
    return np.concatenate((raw[(size + 1) // 2 :], raw[: (size + 1) // 2]))


@pytest.mark.parametrize("bin_index", [5, -9])
def test_theoretical_tone_frequency_power_and_amplitude_ratio(bin_index):
    session = new_session()
    session.append(block(tone(3, bin_index)))
    session.append(block(tone(6, bin_index), 2.0, 2.25))
    report, arrays = session.snapshot()
    peaks = arrays["frequency_hz"][np.argmax(arrays["psd_frames"], axis=1)]
    np.testing.assert_allclose(peaks, [bin_index * FS / N] * 2, atol=1e-10)
    np.testing.assert_allclose(arrays["mean_power"], [9, 36], atol=1e-13)
    np.testing.assert_allclose(arrays["psd_frames"].sum(axis=1) * FS / N, [9, 36])
    np.testing.assert_allclose(arrays["psd_frames"][1], 4 * arrays["psd_frames"][0])
    assert report["relative_db"] == pytest.approx([0, 6.020599913279624])
    assert report["power_reference"] == pytest.approx(9)


def test_blocks_remain_independent_and_host_time_is_not_sample_time():
    session = new_session()
    first, second = tone(2, 5), tone(5, -9)
    session.append(block(first, 0.25, 0.5))
    session.append(block(second, 10.0, 10.25, 11.0, 12.0))
    report, arrays = session.snapshot()
    assert arrays["iq_frames"].shape == (2, N)
    assert arrays["psd_frames"].shape == (2, N)
    assert arrays["frequency_hz"].shape == (N,)
    np.testing.assert_array_equal(arrays["iq_frames"], [first, second])
    np.testing.assert_allclose(arrays["host_rx_start_seconds"], [0.25, 10.0])
    np.testing.assert_allclose(arrays["host_rx_end_seconds"], [0.5, 10.25])
    np.testing.assert_array_equal(arrays["gain_before_db"], [10, 11])
    np.testing.assert_array_equal(arrays["gain_after_db"], [10, 12])
    assert report["host_elapsed_to_last_rx_seconds"] == 10.25
    assert report["observed_blocks_per_host_second"] == pytest.approx(2 / 10.25)
    assert report["sum_of_block_sample_durations_seconds"] == 2 * N / FS
    assert report["received_sample_count"] == 2 * N
    assert report["hardware_gap_sample_count"] is None
    assert report["hardware_continuity_verified"] is False
    assert report["hardware_receive_latency_verified"] is False
    assert report["target_detection_verified"] is False
    assert report["ai_connected"] is False
    assert report["gui_interaction_verified"] is False
    assert report["rf_configuration_written"] is False
    assert report["tx_started"] is False


def test_first_positive_power_is_fixed_reference_and_zero_remains_explicit():
    session = new_session()
    for index, amplitude in enumerate([0, 2, 4, 0, 1]):
        session.append(block(tone(amplitude), index + 0.25, index + 0.5))
    report, arrays = session.snapshot()
    np.testing.assert_allclose(arrays["mean_power"], [0, 4, 16, 0, 1])
    assert report["power_reference"] == pytest.approx(4)
    assert report["relative_db"][0] is None
    assert report["relative_db"][1:3] == pytest.approx([0, 6.020599913279624])
    assert report["relative_db"][3] is None
    assert report["relative_db"][4] == pytest.approx(-6.020599913279624)
    assert report["relative_db_status"] == [
        "no_reference", "finite", "finite", "zero_power", "finite"
    ]
    assert session.relative_db[3] == -np.inf
    assert report["bandwidths"][0]["status"] == "no_effective_power"
    # JSON has an explicit status and null, never nonstandard NaN/Infinity tokens.
    json.dumps(report, allow_nan=False)


def test_all_zero_and_empty_sessions_do_not_fabricate_a_reference_or_rate():
    empty = new_session()
    report, arrays = empty.snapshot()
    assert report["power_reference"] is None
    assert report["observed_blocks_per_host_second"] is None
    assert report["receive_context_released"] is False
    assert arrays["iq_frames"].shape == arrays["psd_frames"].shape == (0, N)
    assert arrays["frequency_hz"].shape == (0,)
    empty.append(block(np.zeros(N, dtype=complex)))
    report, arrays = empty.snapshot()
    assert report["power_reference"] is None
    assert report["relative_db"] == [None]
    assert report["relative_db_status"] == ["no_reference"]
    np.testing.assert_array_equal(arrays["psd_frames"], np.zeros((1, N)))


def test_input_samples_and_snapshot_arrays_do_not_alias_session_storage():
    session = new_session()
    iq = tone().astype(np.complex64)
    expected = iq.copy()
    session.append(block(iq))
    iq[:] = 99 + 99j
    report, arrays = session.snapshot()
    np.testing.assert_array_equal(arrays["iq_frames"][0], expected)
    assert session.blocks[0].iq.dtype == np.complex128
    assert session.blocks[0].iq.flags.writeable is False
    saved_arrays = {name: value.copy() for name, value in arrays.items()}
    for value in arrays.values():
        value[...] = 0
    report["relative_db"][0] = 123
    fresh_report, fresh_arrays = session.snapshot()
    for name, expected_array in saved_arrays.items():
        np.testing.assert_array_equal(fresh_arrays[name], expected_array)
    assert fresh_report["relative_db"] == [0.0]


def test_snapshot_nested_reports_do_not_mutate_future_session_evidence():
    settings = {**SETTINGS, "component_channels": ["voltage0", "voltage1"]}
    session = MonitorSession(settings, fft_size=N)
    session.append(block(tone()))
    report, _ = session.snapshot()
    expected_bandwidth = report["bandwidths"][0]["bandwidth_hz"]
    report["bandwidths"][0]["bandwidth_hz"] = -123
    report["settings"]["component_channels"][0] = "corrupted"
    fresh_report, _ = session.snapshot()
    assert fresh_report["bandwidths"][0]["bandwidth_hz"] == expected_bandwidth
    assert fresh_report["settings"]["component_channels"] == ["voltage0", "voltage1"]


@pytest.mark.parametrize("start,end", [(-0.1, 0.5), (0.5, 0.25), (np.nan, 1), (0, np.inf)])
def test_rejects_invalid_first_host_interval_without_appending(start, end):
    session = new_session()
    with pytest.raises(ValueError):
        session.append(block(tone(), start, end))
    assert len(session.blocks) == 0
    assert session.reference is None


@pytest.mark.parametrize("start,end", [(0.49, 0.75), (0.5, 0.5), (0.25, 0.5), (0.1, 0.2)])
def test_rejects_overlapping_or_nonincreasing_host_intervals(start, end):
    session = new_session()
    session.append(block(tone(), 0.25, 0.5))
    with pytest.raises(ValueError):
        session.append(block(tone(), start, end))
    assert len(session.blocks) == 1


def test_adjacent_nonoverlapping_calls_are_accepted():
    session = new_session()
    session.append(block(tone(), 0.25, 0.5))
    session.append(block(tone(), 0.5, 0.75))
    assert len(session.blocks) == 2


@pytest.mark.parametrize("iq", [
    np.zeros(N), np.zeros((1, N), dtype=complex), np.zeros(N - 1, dtype=complex),
    np.full(N, np.nan + 0j), np.full(N, np.inf + 0j), np.array(["a"] * N),
])
def test_rejects_wrong_shape_real_or_nonfinite_iq(iq):
    session = new_session()
    with pytest.raises(ValueError):
        session.append(block(iq))
    assert len(session.blocks) == 0


@pytest.mark.parametrize("before,after", [(np.nan, 10), (10, np.inf), (-np.inf, 10)])
def test_rejects_nonfinite_gain_readback(before, after):
    with pytest.raises(ValueError):
        new_session().append(block(tone(), before=before, after=after))


@pytest.mark.parametrize("value", [0, -1, 1.5, True, np.bool_(True), np.nan, np.inf, "2"])
def test_frame_limit_is_a_positive_integer(value):
    with pytest.raises(ValueError):
        new_session(frame_limit=value)


@pytest.mark.parametrize("value", [0, 3, -1, 4.5, True, np.bool_(True), np.nan, "64"])
def test_fft_size_is_an_integer_of_at_least_four(value):
    with pytest.raises(ValueError):
        new_session(fft_size=value)


@pytest.mark.parametrize("key", ["sample_rate_hz", "rx_rf_bandwidth_hz"])
@pytest.mark.parametrize("value", [0, -1, np.nan, np.inf])
def test_rejects_nonpositive_or_nonfinite_rates(key, value):
    with pytest.raises(ValueError):
        new_session(**{key: value})


def test_numpy_integer_limits_and_minimum_fft_size_are_accepted():
    session = new_session(frame_limit=np.int64(1), fft_size=np.int32(4))
    session.append(block(tone(size=4, bin_index=1)))
    assert session.snapshot()[1]["iq_frames"].shape == (1, 4)


def test_frame_limit_and_closed_state_stop_further_mutation():
    session = new_session(frame_limit=1)
    session.append(block(tone()))
    with pytest.raises(ValueError, match="accepting"):
        session.append(block(tone(), 1.0, 1.25))
    session = new_session()
    session.state = "stopped"
    with pytest.raises(ValueError, match="accepting"):
        session.append(block(tone()))
    assert len(session.blocks) == 0


class FakeReceiver:
    """An in-memory context: construction/open/read/close are all observable."""

    fft_size = N

    def __init__(self, amplitudes=(2, 4, 8), fail_at=None, on_read=None, exit_error=False):
        self.settings = dict(SETTINGS)
        self.amplitudes = amplitudes
        self.fail_at = fail_at
        self.on_read = on_read
        self.exit_error = exit_error
        self.calls = []
        self.read_count = 0
        self.cleanup_completed = False

    def __enter__(self):
        self.calls.append("enter")
        return self

    def read(self):
        self.calls.append("read")
        index = self.read_count
        self.read_count += 1
        if index == self.fail_at:
            raise RuntimeError("fake receive failed")
        if self.on_read is not None:
            self.on_read(index)
        return block(tone(self.amplitudes[index % len(self.amplitudes)]), 1 + index * 3, 1.25 + index * 3)

    def __exit__(self, exc_type, exc, traceback):
        self.calls.append("exit")
        self.exit_exception = exc
        if self.exit_error:
            raise RuntimeError("fake close failed")
        self.cleanup_completed = True


def test_finite_runner_releases_context_before_final_snapshot():
    receiver = FakeReceiver()
    observed = []

    def on_snapshot(snapshot):
        observed.append((snapshot[0], receiver.cleanup_completed))

    session = run_monitor_session(lambda: receiver, frame_limit=3, interval_seconds=0, on_snapshot=on_snapshot)
    assert receiver.calls == ["enter", "read", "read", "read", "exit"]
    assert session.state == "limit_reached"
    assert session.context_released is True
    assert [report["frame_count"] for report, _ in observed] == [1, 2, 3, 3]
    assert [report["state"] for report, _ in observed] == ["running"] * 3 + ["limit_reached"]
    assert [released for _, released in observed] == [False, False, False, True]
    assert [report["receive_context_released"] for report, _ in observed] == [False, False, False, True]


@pytest.mark.parametrize("stop_before_read", [True, False])
def test_stop_releases_context_and_allows_only_the_inflight_block(stop_before_read):
    stop = Event()
    if stop_before_read:
        stop.set()
    receiver = FakeReceiver(on_read=lambda index: stop.set())
    reports = []
    session = run_monitor_session(lambda: receiver, frame_limit=10, interval_seconds=0,
                                  stop_event=stop, on_snapshot=lambda value: reports.append(value[0]))
    assert session.state == "stopped"
    assert len(session.blocks) == (0 if stop_before_read else 1)
    assert receiver.calls[0] == "enter" and receiver.calls[-1] == "exit"
    assert receiver.calls.count("exit") == 1
    assert session.context_released is True
    assert reports[-1]["state"] == "stopped"
    assert reports[-1]["receive_context_released"] is True


@pytest.mark.parametrize("fail_at", [0, 1, 2])
def test_receive_failure_retains_partial_frames_and_releases_context(fail_at):
    receiver = FakeReceiver(fail_at=fail_at)
    reports = []
    session = run_monitor_session(lambda: receiver, frame_limit=5, interval_seconds=0,
                                  on_snapshot=lambda value: reports.append(value[0]))
    assert session.state == "error"
    assert session.error == "RuntimeError: fake receive failed"
    assert len(session.blocks) == fail_at
    assert receiver.read_count == fail_at + 1
    assert isinstance(receiver.exit_exception, RuntimeError)
    assert receiver.calls[-1] == "exit" and receiver.calls.count("exit") == 1
    assert receiver.cleanup_completed is True
    assert reports[-1]["receive_context_released"] is True
    assert reports[-1]["frame_count"] == fail_at


def test_context_release_failure_is_error_and_does_not_claim_release():
    receiver = FakeReceiver(exit_error=True)
    session = run_monitor_session(lambda: receiver, frame_limit=1, interval_seconds=0)
    assert len(session.blocks) == 1
    assert session.state == "error"
    assert "fake close failed" in session.error
    assert session.snapshot()[0]["receive_context_released"] is False


def test_open_failure_propagates_without_a_fabricated_session():
    def cannot_open():
        raise ConnectionError("fake connection failed")

    with pytest.raises(ConnectionError, match="fake connection failed"):
        run_monitor_session(cannot_open, frame_limit=1, interval_seconds=0)


def test_reopening_uses_new_context_and_new_fixed_reference():
    created = []

    def factory():
        receiver = FakeReceiver(amplitudes=(2 if not created else 8,))
        created.append(receiver)
        return receiver

    first = run_monitor_session(factory, frame_limit=1, interval_seconds=0)
    second = run_monitor_session(factory, frame_limit=1, interval_seconds=0)
    assert first is not second
    assert len(created) == 2 and created[0] is not created[1]
    assert all(receiver.calls == ["enter", "read", "exit"] for receiver in created)
    assert all(receiver.cleanup_completed for receiver in created)
    assert first.reference == pytest.approx(4)
    assert second.reference == pytest.approx(64)
    assert first.relative_db == second.relative_db == [0.0]


def test_poll_interval_is_the_requested_host_wait_not_n_over_fs():
    class RecordingStop:
        def __init__(self):
            self.waits = []

        def is_set(self):
            return False

        def wait(self, timeout):
            self.waits.append(timeout)
            return False

    stop = RecordingStop()
    session = run_monitor_session(lambda: FakeReceiver(), frame_limit=3,
                                  interval_seconds=0.125, stop_event=stop)
    assert stop.waits == [0.125, 0.125]
    assert session.snapshot()[0]["host_elapsed_to_last_rx_seconds"] == 7.25
    assert session.snapshot()[0]["sum_of_block_sample_durations_seconds"] == 3 * N / FS


@pytest.mark.parametrize("interval", [-0.01, np.nan, np.inf, True, np.bool_(True)])
def test_bad_interval_is_rejected_before_opening_receiver(interval):
    def must_not_open():
        pytest.fail("invalid interval must fail before receiver construction")

    with pytest.raises(ValueError):
        run_monitor_session(must_not_open, interval_seconds=interval)


@pytest.mark.parametrize("limit", [0, -1, 1.5, True, np.bool_(True)])
def test_bad_runner_frame_limit_is_rejected_before_opening_receiver(limit):
    def must_not_open():
        pytest.fail("invalid frame limit must fail before receiver construction")

    with pytest.raises(ValueError):
        run_monitor_session(must_not_open, frame_limit=limit)


def test_save_hash_and_raw_arrays_support_independent_recalculation(tmp_path):
    size, fs = 16, 16_000
    session = new_session(fft_size=size, sample_rate_hz=fs, rx_rf_bandwidth_hz=12_000)
    iq = np.array([1 + 2j, -3 + 1j, 0j, 2 - 1j, 1j, -1 - 2j, 4 + 0j, 2j] * 2)
    session.append(block(iq))
    session.append(block(2 * iq, 3, 3.5, 12, 13))
    snapshot = session.snapshot()
    target = save_monitor_snapshot(snapshot, tmp_path / "capture")
    report = json.loads((target / "report.json").read_text(encoding="utf-8"))
    digest = hashlib.sha256((target / "monitor.npz").read_bytes()).hexdigest()
    assert report["arrays_sha256"] == digest
    assert "arrays_sha256" not in snapshot[0]
    assert report["schema"] == "rfsig.rx_monitor.v1"
    assert report["frame_count"] == 2
    with np.load(target / "monitor.npz", allow_pickle=False) as stored:
        expected_frequency = np.arange(-size // 2, size // 2) * fs / size
        np.testing.assert_array_equal(stored["frequency_hz"], expected_frequency)
        np.testing.assert_array_equal(stored["iq_frames"], [iq, 2 * iq])
        np.testing.assert_allclose(stored["host_rx_start_seconds"], [0.25, 3])
        np.testing.assert_allclose(stored["host_rx_end_seconds"], [0.5, 3.5])
        for index in range(2):
            raw = stored["iq_frames"][index]
            expected_power = sum(float(z.real) ** 2 + float(z.imag) ** 2 for z in raw) / size
            assert stored["mean_power"][index] == pytest.approx(expected_power)
            expected_psd = direct_hann_psd(raw, fs)
            np.testing.assert_allclose(stored["psd_frames"][index], expected_psd, rtol=1e-12, atol=1e-15)
            # Check equal tails by integrating each bin cell up to the reported
            # edges, instead of invoking/reimplementing occupied_bandwidth.
            width = fs / size
            low, high = report["analysis_band_hz"]
            left = np.maximum(expected_frequency - width / 2, low)
            right = np.minimum(expected_frequency + width / 2, high)
            coverage = np.maximum(right - left, 0)
            total = np.dot(expected_psd, coverage)
            band = report["bandwidths"][index]
            for edge, fraction in [(band["lower_hz"], 0.005), (band["upper_hz"], 0.995)]:
                cumulative = np.dot(expected_psd, np.clip(edge - left, 0, coverage))
                assert cumulative == pytest.approx(total * fraction, rel=1e-11, abs=1e-13)
            assert band["observed_region_power"] == pytest.approx(total)
            assert band["center_rf_hz"] == pytest.approx(SETTINGS["rx_lo_hz"] + band["center_baseband_hz"])


def test_save_refuses_existing_directory_and_leaves_first_capture_unchanged(tmp_path):
    session = new_session()
    session.append(block(tone()))
    target = save_monitor_snapshot(session.snapshot(), tmp_path / "capture")
    originals = {path.name: path.read_bytes() for path in target.iterdir()}
    session.append(block(tone(4), 1, 1.25))
    with pytest.raises(FileExistsError):
        save_monitor_snapshot(session.snapshot(), target)
    assert {path.name: path.read_bytes() for path in target.iterdir()} == originals


def test_empty_save_fails_without_creating_a_directory(tmp_path):
    target = tmp_path / "empty"
    with pytest.raises(ValueError, match="No RX frame"):
        save_monitor_snapshot(new_session().snapshot(), target)
    assert not target.exists()


def test_zero_power_save_has_standards_compliant_json(tmp_path):
    session = new_session()
    session.append(block(np.zeros(N, dtype=complex)))
    session.append(block(tone(), 1, 1.25))
    session.append(block(np.zeros(N, dtype=complex), 2, 2.25))
    target = save_monitor_snapshot(session.snapshot(), tmp_path / "zero")

    def reject_constant(value):
        pytest.fail(f"JSON contains nonstandard constant {value}")

    report = json.loads((target / "report.json").read_text(encoding="utf-8"), parse_constant=reject_constant)
    assert report["relative_db"] == [None, 0, None]
    assert report["relative_db_status"] == ["no_reference", "finite", "zero_power"]


class RawSDR:
    def __init__(self, iq, gains=(10, 10)):
        self.iq = np.asarray(iq)
        self.gains = iter(gains)
        self.read_count = 0

    @property
    def rx_hardwaregain_chan0(self):
        return next(self.gains)

    def rx(self):
        self.read_count += 1
        return self.iq


def raw_receiver(monkeypatch, iq, gains=(10, 10), mode="slow_attack", after_changes=None):
    receiver = P201Receiver("unused-offline-directory", fft_size=N)
    receiver.sdr = RawSDR(iq, gains)
    receiver.initial_settings = {**SETTINGS, "gain_control_mode": mode}
    receiver.initial_gain_db = 10
    settings = iter([dict(receiver.initial_settings), {**receiver.initial_settings, **(after_changes or {})}])
    monkeypatch.setattr(receiver, "_settings", lambda: next(settings))
    return receiver


def test_p201_read_preserves_raw_signed_12bit_counts_and_copies_input(monkeypatch):
    iq = np.tile(np.array([-2048 + 2047j, 2047 - 2048j, 0j, 1 - 1j]), N // 4)
    receiver = raw_receiver(monkeypatch, iq, gains=(10, 13))
    clock = iter([77.0, 77.25])
    monkeypatch.setattr(monitor, "perf_counter", lambda: next(clock))
    received = receiver.read()
    assert (received.host_start, received.host_end) == (77.0, 77.25)
    assert (received.gain_before_db, received.gain_after_db) == (10, 13)
    np.testing.assert_array_equal(received.iq, iq)
    receiver.sdr.iq[:] = 0
    assert np.any(received.iq != 0)


@pytest.mark.parametrize("iq", [
    np.zeros(N), np.zeros(N - 1, dtype=complex), np.full(N, np.nan + 0j),
    np.full(N, 2048 + 0j), np.full(N, -2049j), np.full(N, 0.25 + 1j),
])
def test_p201_read_rejects_unverified_raw_representation(monkeypatch, iq):
    receiver = raw_receiver(monkeypatch, iq)
    with pytest.raises(RuntimeError, match="format|representation"):
        receiver.read()


@pytest.mark.parametrize("gains,expected_read_count", [((11, 11), 0), ((10, 11), 1)])
def test_p201_manual_gain_change_stops_before_or_after_capture(monkeypatch, gains, expected_read_count):
    receiver = raw_receiver(monkeypatch, np.zeros(N, dtype=complex), gains=gains, mode="manual")
    with pytest.raises(RuntimeError, match="Manual RX gain changed"):
        receiver.read()
    assert receiver.sdr.read_count == expected_read_count


def test_p201_configuration_change_during_capture_is_rejected(monkeypatch):
    receiver = raw_receiver(monkeypatch, np.zeros(N, dtype=complex), after_changes={"rx_lo_hz": 123_000_000})
    with pytest.raises(RuntimeError, match="configuration changed during"):
        receiver.read()


@pytest.mark.parametrize("failing_cleanup", [None, "destroy", "close", "scope"])
def test_p201_cleanup_attempts_every_release_and_clears_handles(failing_cleanup):
    receiver = P201Receiver("unused-offline-directory", fft_size=N)
    calls = []

    def release(name):
        calls.append(name)
        if name == failing_cleanup:
            raise OSError(f"fake {name} failure")

    receiver.sdr = SimpleNamespace(rx_destroy_buffer=lambda: release("destroy"), close=lambda: release("close"))
    receiver.scope = SimpleNamespace(__exit__=lambda *args: release("scope"))
    if failing_cleanup is None:
        receiver.__exit__(None, None, None)
    else:
        with pytest.raises(RuntimeError, match=f"fake {failing_cleanup} failure"):
            receiver.__exit__(None, None, None)
    assert calls == ["destroy", "close", "scope"]
    assert receiver.sdr is None and receiver.scope is None
    assert receiver.cleanup_completed is (failing_cleanup is None)


def test_p201_cleanup_failure_attaches_note_without_masking_original_read_error():
    receiver = P201Receiver("unused-offline-directory", fft_size=N)
    calls = []

    def bad_destroy():
        calls.append("destroy")
        raise OSError("fake buffer destruction failure")

    receiver.sdr = SimpleNamespace(rx_destroy_buffer=bad_destroy, close=lambda: calls.append("close"))
    receiver.scope = SimpleNamespace(__exit__=lambda *args: calls.append("scope"))
    original = RuntimeError("original receive failure")
    receiver.__exit__(RuntimeError, original, None)
    assert str(original) == "original receive failure"
    assert any("fake buffer destruction failure" in note for note in original.__notes__)
    assert calls == ["destroy", "close", "scope"]
    assert receiver.cleanup_completed is False
