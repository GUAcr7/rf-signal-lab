"""Compile and exercise native TX lifecycle against a PRIVATE in-memory mock.

Run with Linux Python (for example WSL Ubuntu). Never opens a board or real IIO
backend. The output is host mock evidence only, not RF/deadline hardware evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import shutil
import struct
import subprocess
import sys
import time
import tempfile
from datetime import datetime, timezone


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if sys.platform != "linux":
        raise SystemExit("Run this HOST MOCK test using Linux Python, e.g. WSL; no board is used.")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = (args.output or root / "results" / f"p12-native-mock-{timestamp}").resolve()
    if output.parent != (root / "results").resolve() or output.exists():
        raise SystemExit("Output must be a NEW direct child of project/results.")
    output.mkdir()
    build = output / "mock-only-build"
    build.mkdir()
    header_dir = root / "embedded/vendor/libiio-v0.24"
    source = root / "embedded/arm_tx_source/arm_tx_source.c"
    mock_source = root / "tests/native/tx_mock_iio.c"
    executable = build / "arm_tx_source_host_mock_test"
    library = build / "libiio.so.0"
    source_hashes = {str(p.relative_to(root)): sha256(p) for p in (source, mock_source, Path(__file__).resolve(), header_dir / "iio.h")}
    report = {
        "status": "running", "kind": "HOST_IN_MEMORY_MOCK_ONLY_NOT_RF",
        "real_device_access": False, "real_rf_transmission": False,
        "source_sha256_before": source_hashes, "cases": [],
        "limitations": ["No real libiio backend, board, DMA, DAC, RF, or hardware interlock is tested.",
                        "Deadline results describe a Linux host scheduling/cancellation simulation only.",
                        "RF_LINK_REVIEWED is deliberately used ONLY with this private mock library."],
    }
    report_file = output / "report.json"

    def save() -> None:
        report_file.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    def compile_one(name: str, command: list[str]) -> None:
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        (output / f"{name}.stdout.txt").write_text(result.stdout, encoding="utf-8")
        (output / f"{name}.stderr.txt").write_text(result.stderr, encoding="utf-8")
        report.setdefault("compilation", []).append({"name": name, "command": command, "exit_code": result.returncode})
        save()
        if result.returncode:
            raise AssertionError(f"{name} failed; preserved compiler logs")

    def events_at(path: Path) -> list[dict]:
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    def case(name: str, argv: list[str], *, scenario: str = "normal", expected_success: bool,
             no_context: bool = False, no_mutation: bool = False, local_mask_cleanup_only: bool = False, created: bool = False,
             create_failed: bool = False, pushed: bool = False, dds_clean: bool = False,
             signal_after_push: bool = False, deadline: bool = False) -> None:
        case_dir = output / name
        case_dir.mkdir()
        # Keep scheduling-sensitive log I/O on Linux's filesystem, not WSL /mnt/c.
        temporary = tempfile.TemporaryDirectory(prefix="rfsig-tx-mock-")
        log = Path(temporary.name) / "mock-events.jsonl"
        env = dict(os.environ)
        env.update(LD_LIBRARY_PATH=str(build), MOCK_IIO_ISOLATED="1", MOCK_IIO_LOG=str(log), MOCK_IIO_SCENARIO=scenario)
        # Remove preloads/auditors inherited from a shell; only the private mock resolves libiio.
        env.pop("LD_PRELOAD", None)
        env.pop("LD_AUDIT", None)
        started = time.monotonic()
        process = subprocess.Popen([str(executable), *argv], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        timed_out = False
        sent_signal = False
        try:
            if signal_after_push:
                wait_deadline = started + 1.0
                while time.monotonic() < wait_deadline and process.poll() is None:
                    if any(e["event"] == "buffer_push" for e in events_at(log)):
                        process.send_signal(signal.SIGTERM)
                        sent_signal = True
                        break
                    time.sleep(0.005)
                if not sent_signal:
                    raise AssertionError("Mock child did not enter buffer_push before SIGTERM check")
            stdout, stderr = process.communicate(timeout=max(0.01, 3.0 - (time.monotonic() - started)))
        except subprocess.TimeoutExpired:
            timed_out = True
            process.kill()  # This PID is the just-created host MOCK child only.
            stdout, stderr = process.communicate()
        except BaseException:
            process.kill()
            stdout, stderr = process.communicate()
            (case_dir / "stdout.txt").write_text(stdout, encoding="utf-8")
            (case_dir / "stderr.txt").write_text(stderr, encoding="utf-8")
            raise
        elapsed = time.monotonic() - started
        (case_dir / "stdout.txt").write_text(stdout, encoding="utf-8")
        (case_dir / "stderr.txt").write_text(stderr, encoding="utf-8")
        events = events_at(log)
        if log.exists():
            shutil.copyfile(log, case_dir / "mock-events.jsonl")
        temporary.cleanup()
        names = [e["event"] for e in events]
        checks = {
            "no_outer_timeout": not timed_out,
            "exit_matches_expectation": (process.returncode == 0) == expected_success,
            "no_forbidden_attribute_write": "FORBIDDEN_WRITE" not in names,
            "only_mock_library_loaded": no_context or names.count("mock_library_loaded") == 1,
        }
        if no_context:
            checks["no_context_and_no_dlopen"] = not events
        else:
            checks["one_context_created_and_destroyed"] = names.count("context_create") == names.count("context_destroy") == 1
            checks["context_destroy_last_event"] = bool(names) and names[-1] == "context_destroy"
        if no_mutation:
            checks["no_mutating_calls"] = not any(n in names for n in ("dds_raw_zero_write", "channel_enable", "channel_disable", "buffer_create", "buffer_push"))
        if local_mask_cleanup_only:
            checks["no_rf_dds_enable_or_buffer_actions"] = not any(n in names for n in ("dds_raw_zero_write", "channel_enable", "buffer_create", "buffer_push"))
            checks["only_twelve_local_dac_mask_disables"] = names.count("channel_disable") == 12
        if created:
            checks["one_buffer_created"] = names.count("buffer_create") == 1
            checks["one_buffer_destroyed"] = names.count("buffer_destroy") == 1
            checks["cancel_before_destroy"] = "buffer_cancel" in names and "buffer_destroy" in names and names.index("buffer_cancel") < names.index("buffer_destroy")
            checks["destroy_before_context"] = "buffer_destroy" in names and "context_destroy" in names and names.index("buffer_destroy") < names.index("context_destroy")
            # Every DAC channel must be disabled again after buffer destruction.
            tail = events[names.index("buffer_destroy") + 1:] if "buffer_destroy" in names else []
            checks["all_twelve_dac_channels_disabled_on_exit"] = sum(e["event"] == "channel_disable" for e in tail) == 12
        if create_failed:
            checks["failed_create_has_no_destroy_or_push"] = names.count("buffer_create") == 1 and not any(n in names for n in ("buffer_destroy", "buffer_push"))
        checks["push_matches_expectation"] = ("buffer_push" in names) == pushed
        if dds_clean:
            writes = [e for e in events if e["event"] == "dds_raw_zero_write"]
            checks["dds_zero_before_and_after"] = len(writes) == 16 and all(sum(e["detail"] == f"altvoltage{j}" for e in writes) == 2 for j in range(8))
            checks["dds_zero_readback_passed_twice"] = stdout.count("DDS_ZERO_SOURCE_READBACK=PASS") == 2
            checks["dds_zero_before_create"] = "buffer_create" in names and names[:names.index("buffer_create")].count("dds_raw_zero_write") == 8
            if created:
                checks["no_dds_write_while_buffer_alive"] = "buffer_destroy" in names and "dds_raw_zero_write" not in names[names.index("buffer_create") + 1:names.index("buffer_destroy")]
                checks["dds_zero_after_destroy"] = "buffer_destroy" in names and names[names.index("buffer_destroy") + 1:].count("dds_raw_zero_write") == 8
        if deadline:
            checks["local_duration_bounded_0_07_to_1_0_seconds"] = 0.07 <= elapsed < 1.0
            checks["watchdog_cancel_observed"] = names.count("buffer_cancel") >= 2
        if scenario == "push_block":
            checks["blocked_push_released_by_cancel"] = "buffer_push_unblocked_by_cancel" in names
        if signal_after_push:
            checks["sigterm_sent_to_mock_child"] = sent_signal
            checks["sigterm_stopped_within_one_second"] = elapsed < 1.0
        if scenario == "dds_write_fail":
            checks["dds_failure_detected_both_attempts"] = names.count("dds_raw_zero_failed") == 2 and stdout.count("DDS_ZERO_SOURCE_READBACK=FAILED") == 2
        entry = {"name": name, "scenario": scenario, "argv": argv, "exit_code": process.returncode,
                 "elapsed_seconds": elapsed, "outer_timeout_kill": timed_out, "sigterm_sent": sent_signal,
                 "event_count": len(events), "checks": checks, "passed": all(checks.values())}
        report["cases"].append(entry)
        save()
        print(f"MOCK {'PASS' if entry['passed'] else 'FAIL'} {name} exit={process.returncode} elapsed={elapsed:.3f}s", flush=True)

    try:
        compile_one("compile-mock", ["gcc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-fPIC", "-shared", "-pthread", "-I", str(header_dir), str(mock_source), "-o", str(library)])
        compile_one("compile-native", ["gcc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-pthread", "-I", str(header_dir), str(source), "-ldl", "-lm", "-o", str(executable)])
        report["binaries_sha256"] = {p.name: sha256(p) for p in (library, executable)}
        sample_file = output / "valid-left-aligned-s12-iq.bin"
        sample_file.write_bytes(b"".join(struct.pack("<hh", i * 16, q * 16) for i, q in [(0, 0), (128, -128), (2047, -2048), (-256, 256)] * 64))
        count = "256"
        sample_hash = sha256(sample_file)
        report["input"] = {"file": sample_file.name, "samples": 256, "sha256": sample_hash, "generator": "Python struct.pack <hh, signed12 components multiplied by16"}
        valid_run = ["--run", str(sample_file), count, "30720000", "2400000000", "18000000", "-40", "0.1", "MOCK-P201-001", "A", sample_hash, "RF_LINK_REVIEWED"]
        case("sha256-selftest", ["--sha256-selftest"], expected_success=True, no_context=True)
        case("file-check-valid", ["--check", str(sample_file), count, sample_hash], expected_success=True, no_context=True)
        case("inspect-readonly", ["--inspect"], expected_success=True, no_mutation=True)
        case("inspect-nonzero-dds-readonly", ["--inspect"], scenario="dds_scale_nonzero", expected_success=True, no_mutation=True)
        case("normal-local-deadline", valid_run, expected_success=True, created=True, pushed=True, dds_clean=True, deadline=True)
        for failure in ("model_mismatch", "serial_mismatch", "dds_scale_nonzero", "tx_dma_rate_missing"):
            case(f"reject-{failure}", valid_run, scenario=failure, expected_success=False, no_mutation=True)
        for failure in ("rf_mismatch", "port_mismatch", "tx_dma_rate_mismatch"):
            case(f"reject-{failure}", valid_run, scenario=failure, expected_success=False, local_mask_cleanup_only=True)
        case("create-fails", valid_run, scenario="create_fail", expected_success=False, create_failed=True, dds_clean=True)
        for failure in ("step_fail", "first_fail"):
            case(f"cleanup-{failure}", valid_run, scenario=failure, expected_success=False, created=True, dds_clean=True)
        case("cleanup-push-error", valid_run, scenario="push_error", expected_success=False, created=True, pushed=True, dds_clean=True)
        case("deadline-cancels-blocked-push", valid_run, scenario="push_block", expected_success=False, created=True, pushed=True, dds_clean=True, deadline=True)
        case("reject-dds-write-fails", valid_run, scenario="dds_write_fail", expected_success=False)
        signal_run = valid_run.copy()
        signal_run[7] = "2"
        case("sigterm-normal-push", signal_run, expected_success=True, created=True, pushed=True, dds_clean=True, signal_after_push=True)
        case("sigterm-blocked-push", signal_run, scenario="push_block", expected_success=False, created=True, pushed=True, dds_clean=True, signal_after_push=True)
        for name, index, value in [("sample-count", 2, "0"), ("fs", 3, "0"), ("lo", 4, "1"), ("gain", 6, "1"), ("duration", 7, "61"), ("duration-nan", 7, "nan"), ("serial-empty", 8, ""), ("port", 9, "C"), ("hash-syntax", 10, "x"), ("hash-mismatch", 10, "0" * 64), ("review-token", 11, "UNREVIEWED")]:
            bad = valid_run.copy()
            bad[index] = value
            case(f"precontext-reject-{name}", bad, expected_success=False, no_context=True)
        bad_low = output / "invalid-low-bits.bin"
        raw = bytearray(sample_file.read_bytes()); raw[0] = 1; bad_low.write_bytes(raw)
        bad = valid_run.copy(); bad[1] = str(bad_low); bad[10] = sha256(bad_low)
        case("precontext-reject-low-bits", bad, expected_success=False, no_context=True)
        bad = valid_run.copy()
        bad[1] = str(output / "missing.bin")
        case("precontext-reject-missing-file", bad, expected_success=False, no_context=True)
        short_file = output / "short.bin"; short_file.write_bytes(sample_file.read_bytes()[:-4])
        bad = valid_run.copy(); bad[1] = str(short_file); bad[10] = sha256(short_file)
        case("precontext-reject-file-length", bad, expected_success=False, no_context=True)
        report["source_sha256_after"] = {name: sha256(root / name) for name in source_hashes}
        report["sources_unchanged_during_test"] = report["source_sha256_after"] == source_hashes
        report["passed_count"] = sum(case["passed"] for case in report["cases"])
        report["case_count"] = len(report["cases"])
        report["status"] = "passed_host_mock_only" if all(case["passed"] for case in report["cases"]) and report["sources_unchanged_during_test"] else "failed_host_mock_only"
    except BaseException as error:
        report["status"] = "failed_host_mock_only"
        report["error"] = f"{type(error).__name__}: {error}"
        save()
        raise
    save()
    print(json.dumps({"report": str(report_file), "status": report["status"], "passed": report["passed_count"], "total": report["case_count"]}), flush=True)
    return 0 if report["status"] == "passed_host_mock_only" else 1


if __name__ == "__main__":
    raise SystemExit(main())
