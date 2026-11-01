"""Pure runner validation against actual native-C mock output; no serial use."""
import copy
import importlib.util
import json
from pathlib import Path
import sys

import pytest

from test_native_rx_full_p36 import built, invoke, metadata

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
spec = importlib.util.spec_from_file_location("p36_full_rx_offline_runner", ROOT / "experiments/p36_full_rx_run.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


@pytest.fixture
def native_result(built, tmp_path):
    result, out, _ = invoke(built, tmp_path, count=1)
    assert result.returncode == 0
    return result.stdout.decode(), metadata(out)


def test_runner_accepts_actual_C_output_and_metadata_without_opening_serial(native_result, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("offline validation tried to open serial")
    monkeypatch.setattr(runner, "BoardConsole", forbidden)
    text, meta = native_result
    start, completion = runner.validate_completion(text, 1)
    assert start["requested_blocks"] == completion["completed_blocks"] == 1
    assert runner.validate_metadata(meta, 1) is meta


@pytest.mark.parametrize("field,value", [
    ("lossless_proven", True), ("hardware_gaps", "none"), ("adc_first_sample_counter", 0),
    ("scan_layout_validated", False), ("rf_after_matches", False), ("complete_stream_saved", True),
    ("raw_file_bytes_written", 4), ("requested_blocks", True), ("buffer_released", False),
    ("worker_joined", False), ("cleanup_unconfirmed", True), ("RF_attributes_written", True),
    ("storage", "sign_extended_int16"),
])
def test_runner_rejects_false_completion_contract(native_result, field, value):
    _, meta = native_result
    changed = copy.deepcopy(meta)
    changed[field] = value
    with pytest.raises(ValueError):
        runner.validate_metadata(changed, 1)


@pytest.mark.parametrize("kind", ["failed_copy", "wrong_offset", "short_bytes", "reverse_time", "nan_time", "missing_stamp"])
def test_runner_rejects_invalid_per_buffer_evidence(native_result, kind):
    _, meta = native_result
    changed = copy.deepcopy(meta)
    stamp = changed["timestamps"][0]
    if kind == "failed_copy":
        stamp["copy_complete"] = False
    elif kind == "wrong_offset":
        stamp["file_byte_offset"] = 4
    elif kind == "short_bytes":
        stamp["refill_bytes"] -= 4
    elif kind == "reverse_time":
        stamp["copy_end_s"] = -1
    elif kind == "nan_time":
        stamp["refill_end_s"] = float("nan")
    else:
        changed["timestamps"] = []
    with pytest.raises(ValueError):
        runner.validate_metadata(changed, 1)


def test_runner_rejects_missing_duplicate_or_failed_completion(native_result):
    text, _ = native_result
    rows = runner.json_rows(text)
    for changed in [rows[:-1], rows + [rows[-1]], [rows[0], dict(rows[-1], exit_status=1)]]:
        with pytest.raises(ValueError):
            runner.validate_completion("\n".join(json.dumps(row) for row in changed), 1)


def test_untrusted_build_report_path_is_rejected_locally_without_serial(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "BoardConsole", lambda *args: pytest.fail("serial opened"))
    report = tmp_path / "report.json"
    report.write_text("{}")
    with pytest.raises(ValueError, match="local results"):
        runner.load_build(report)
