"""Exercise the actual P36 C recorder with mock IIO; never access a board."""
import json
import os
from pathlib import Path
import subprocess

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
BLOCK_FRAMES = 65536
BLOCK_BYTES = BLOCK_FRAMES * 4


def posix(path):
    value = Path(path).resolve().as_posix()
    return "/mnt/" + value[0].lower() + value[2:] if os.name == "nt" else value


def run(command, timeout=45):
    prefix = ["wsl.exe", "--exec"] if os.name == "nt" else []
    return subprocess.run(prefix + command, capture_output=True, timeout=timeout)


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    directory = tmp_path_factory.mktemp("native-full-p36")
    include = ROOT / "embedded/vendor/libiio-v0.24"
    sources = [
        (ROOT / "tests/native/mock_rx_full_p36.c", directory / "libiio.so.0", ["-shared", "-fPIC"]),
        (ROOT / "embedded/arm_rx_full_p36/arm_rx_full_p36.c", directory / "receiver", ["-ldl", "-lrt", "-pthread"]),
    ]
    for source, target, flags in sources:
        result = run(["gcc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-I", posix(include), posix(source), "-o", posix(target), *flags])
        assert result.returncode == 0, result.stdout.decode(errors="replace") + result.stderr.decode(errors="replace")
    return directory


def invoke(built, tmp_path, fault="", count=None):
    output = tmp_path / "output"
    log = tmp_path / "cleanup.txt"
    command = ["env", "LD_LIBRARY_PATH=" + posix(built), "P36_MOCK_LOG=" + posix(log), "P36_MOCK_FAULT=" + fault,
               posix(built / "receiver"), posix(output)]
    if count is not None:
        command.append(str(count))
    return run(command), output, log


def metadata(output):
    return json.loads((output / "metadata.json").read_text())


def test_default_saves_all_original_bytes_in_all_sixteen_blocks(built, tmp_path):
    result, out, log = invoke(built, tmp_path)
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    words = np.fromfile(out / "iq-packed.bin", dtype="<u2").reshape(16, BLOCK_FRAMES, 2)
    position = (np.arange(16)[:, None] * 97 + np.arange(BLOCK_FRAMES)[None, :]) % 4096
    np.testing.assert_array_equal(words[:, :, 0], position | ((np.arange(16)[:, None] & 15) << 12))
    np.testing.assert_array_equal(words[:, :, 1], (4095 - position) | (((np.arange(16)[:, None] + 5) & 15) << 12))
    # Signal interpretation masks the undefined high bits; both signs occur.
    signed = ((words & 4095).astype(np.int16) ^ 2048) - 2048
    assert signed.min() == -2048 and signed.max() == 2047
    meta = metadata(out)
    assert meta["raw_expected_bytes"] == meta["raw_file_bytes_written"] == 4 * 1024 * 1024
    assert meta["complete_returned_buffers_saved"] is True
    assert meta["requested_capture_complete"] is True
    assert meta["complete_stream_saved"] is False and meta["lossless_proven"] is False
    assert meta["hardware_gaps"] == "unknown" and meta["adc_first_sample_counter"] is None
    assert meta["worker_joined"] is True and meta["rf_after_matches"] is True
    assert meta["scan_layout_validated"] is True
    assert len(meta["timestamps"]) == 16
    previous = 0
    for j, stamp in enumerate(meta["timestamps"]):
        assert stamp["block_index"] == j and stamp["file_byte_offset"] == j * BLOCK_BYTES
        assert stamp["refill_bytes"] == BLOCK_BYTES and stamp["copy_complete"] is True
        assert previous <= stamp["refill_start_s"] <= stamp["refill_end_s"] <= stamp["copy_end_s"]
        previous = stamp["copy_end_s"]
    assert "destroyed=1 enabled=0 created=1 refills=16" in log.read_text()
    assert (out / "before.txt").read_bytes() == (out / "after.txt").read_bytes()


@pytest.mark.parametrize("fault", ["version", "config", "format", "bist", "empty_bist", "sample_size", "create"])
def test_preflight_failures_do_not_pass_or_return_samples(built, tmp_path, fault):
    result, out, log = invoke(built, tmp_path, fault)
    assert result.returncode == 1
    meta = metadata(out)
    assert meta["status"] == "fail" and meta["completed_blocks"] == 0
    assert meta["requested_capture_complete"] is False and meta["lossless_proven"] is False
    assert meta["scan_layout_validated"] is (fault == "create")
    assert (out / "iq-packed.bin").stat().st_size == 0
    if log.exists():
        assert "enabled=0" in log.read_text()


@pytest.mark.parametrize("fault", ["step", "end", "iq_offset", "null_i"])
def test_layout_errors_are_rejected_before_copy(built, tmp_path, fault):
    result, out, log = invoke(built, tmp_path, fault)
    assert result.returncode == 1
    meta = metadata(out)
    assert meta["reason"] == "refill_layout_mismatch" and meta["completed_blocks"] == 0
    assert meta["attempted_refills"] == 1 and meta["timestamps"][0]["copy_complete"] is False
    assert "destroyed=1 enabled=0" in log.read_text()


@pytest.mark.parametrize("fault", ["refill", "short"])
def test_partial_capture_keeps_only_finished_blocks_and_failed_attempt(built, tmp_path, fault):
    result, out, log = invoke(built, tmp_path, fault)
    assert result.returncode == 1
    meta = metadata(out)
    assert meta["completed_blocks"] == 3 and meta["attempted_refills"] == 4
    assert (out / "iq-packed.bin").stat().st_size == 3 * BLOCK_BYTES
    assert meta["complete_returned_buffers_saved"] is True and meta["requested_capture_complete"] is False
    assert meta["timestamps"][-1]["copy_complete"] is False
    assert "destroyed=1 enabled=0" in log.read_text()


def test_after_rf_change_fails_despite_complete_bytes(built, tmp_path):
    result, out, _ = invoke(built, tmp_path, "after_config")
    assert result.returncode == 1
    meta = metadata(out)
    assert meta["reason"] == "rf_after_mismatch_or_failure" and meta["rf_after_matches"] is False
    assert meta["complete_returned_buffers_saved"] is True and meta["requested_capture_complete"] is False
    assert meta["completed_blocks"] == 16
    assert "gain_mode=slow_attack\n" in (out / "after.txt").read_text()
    assert "gain_mode_read_ok=true\n" in (out / "after.txt").read_text()


def test_signal_cancels_in_normal_main_thread_and_saves_partial_data(built, tmp_path):
    result, out, log = invoke(built, tmp_path, "cancel")
    assert result.returncode == 1
    meta = metadata(out)
    assert meta["cancel_requested"] is True and meta["worker_joined"] is True
    assert meta["completed_blocks"] == 3 and meta["signal_requested_stop"] is True
    assert meta["timestamps"][-1]["refill_bytes"] < 0
    assert "destroyed=1 enabled=0" in log.read_text()


def test_join_failure_does_not_destroy_live_worker_buffer_or_context(built, tmp_path):
    result, out, log = invoke(built, tmp_path, "join_hang")
    assert result.returncode == 3
    completion = json.loads(result.stdout.decode().splitlines()[-1])
    assert completion["cleanup_unconfirmed"] is True and completion["status"] == "join_failed"
    assert not log.exists() and not list(out.iterdir())


@pytest.mark.parametrize("count", ["0", "65", "-1", "16junk", "", "18446744073709551616"])
def test_invalid_or_unbounded_counts_do_not_create_output(built, tmp_path, count):
    result, out, _ = invoke(built, tmp_path, count=count)
    assert result.returncode == 2 and not out.exists()


def test_existing_directory_is_rejected_without_changing_artifacts(built, tmp_path):
    result, out, _ = invoke(built, tmp_path, count=1)
    assert result.returncode == 0
    before = {p.name: p.read_bytes() for p in out.iterdir()}
    result, _, _ = invoke(built, tmp_path, count=1)
    assert result.returncode == 2
    assert before == {p.name: p.read_bytes() for p in out.iterdir()}


def test_maximum_request_is_bounded_and_keeps_each_buffer(built, tmp_path):
    result, out, _ = invoke(built, tmp_path, count=64)
    assert result.returncode == 0
    meta = metadata(out)
    assert meta["completed_blocks"] == len(meta["timestamps"]) == 64
    assert (out / "iq-packed.bin").stat().st_size == 16 * 1024 * 1024
