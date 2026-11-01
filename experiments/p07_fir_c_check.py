"""Host-only C99 FIR compilation and exact saved-vector comparison; no board access."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from time import perf_counter

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from rfsig.fixed_fir import apply_fixed_fir_full, quantize_accumulator


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_case(root, entry, original):
    directory = (root / entry["directory"]).resolve()
    if not directory.is_relative_to(root):
        raise ValueError("Case directory escapes vector root")
    case = json.loads((directory / "case.json").read_text(encoding="utf-8"))
    if case != original:
        raise ValueError("Case metadata differs from saved reference report")
    for key in ("name", "input_count", "tap_count", "expected_output_count"):
        if case[key] != entry[key]:
            raise ValueError(f"Manifest disagrees with case: {key}")
    if (case["input_bits"], case["coefficient_bits"], case["coefficient_fractional_bits"], case["accumulator_bits"], case["output_bits"]) != (12, 18, 17, 36, 16):
        raise ValueError("Unsupported arithmetic contract")
    if not 1 <= case["tap_count"] <= 63 or case["input_count"] < 1 or case["expected_output_count"] != case["input_count"] + case["tap_count"] - 1:
        raise ValueError("Invalid tap/sample/tail count")
    required = {"coefficients.hex", "input_i.hex", "input_q.hex", "expected_i.hex", "expected_q.hex", "saturated_i.hex", "saturated_q.hex"}
    if {spec["name"] for spec in case["files"]} != required or len(case["files"]) != 7:
        raise ValueError("Unexpected vector-file set")
    loaded, verified = {}, []
    for spec in case["files"]:
        path = (directory / spec["name"]).resolve()
        if not path.is_relative_to(directory) or digest(path) != spec["sha256"]:
            raise ValueError(f"Modified vector file: {path}")
        lines = path.read_text(encoding="ascii").splitlines()
        bits = {"coefficients.hex": 18, "input_i.hex": 12, "input_q.hex": 12, "expected_i.hex": 16, "expected_q.hex": 16, "saturated_i.hex": 1, "saturated_q.hex": 1}[spec["name"]]
        expected_words = case["tap_count"] if spec["name"] == "coefficients.hex" else case["input_count"] if spec["name"].startswith("input_") else case["expected_output_count"]
        if spec["bits"] != bits or spec["words"] != expected_words or len(lines) != expected_words or any(not re.fullmatch(r"[0-9a-fA-F]{1,%d}" % ((bits + 3)//4), line) or int(line, 16) >= 1 << bits for line in lines):
            raise ValueError(f"Malformed vector word/count: {path}")
        values = [int(line, 16) for line in lines]
        if not spec["name"].startswith("saturated_"):
            values = [value - (1 << bits) if value >= 1 << (bits-1) else value for value in values]
        loaded[spec["name"]] = np.asarray(values, dtype=np.int64)
        verified.append({"name": spec["name"], "sha256": spec["sha256"], "words": len(lines)})
    return directory, case, loaded, verified


def run(command, env, logfile, *, allow_failure=False):
    start = perf_counter()
    process = subprocess.run([str(x) for x in command], cwd=ROOT, env=env, capture_output=True, text=True, encoding="ascii", errors="replace", timeout=60)
    logfile.write_text(process.stdout + process.stderr, encoding="utf-8")
    if not allow_failure and (process.returncode != 0 or process.stderr):
        raise RuntimeError(f"Host command failed/diagnosed: {logfile}")
    return process, perf_counter()-start


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("vectors", type=Path)
    parser.add_argument("--gcc", type=Path, default=Path(r"C:\msys64\ucrt64\bin\gcc.exe"))
    args = parser.parse_args()
    vectors, gcc = args.vectors.resolve(), args.gcc.resolve()
    original = json.loads((vectors / "report.json").read_text(encoding="utf-8"))
    manifest = json.loads((vectors / "manifest.json").read_text(encoding="utf-8"))
    if len(manifest["cases"]) != 18 or len({entry["name"] for entry in manifest["cases"]}) != 18:
        raise ValueError("Require all 18 distinct saved cases")
    reference_cases = {case["name"]: case for case in original["cases"]}
    # Verify every saved input/expected file before compiling or executing C.
    cases = [verify_case(vectors, entry, reference_cases[entry["name"]]) for entry in manifest["cases"]]
    if digest(ROOT / "src/rfsig/fixed_fir.py") != original["code_sha256"]["src/rfsig/fixed_fir.py"]:
        raise ValueError("Python arithmetic reference changed after vector generation")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = ROOT / "results" / f"p07-c-reference-{stamp}"
    output.mkdir(parents=True, exist_ok=False)
    sources = [ROOT / "embedded/fir_reference" / name for name in ("fixed_fir.h", "fixed_fir.c", "fir_hex_cli.c", "README.md")]
    sources += [Path(__file__), ROOT / "src/rfsig/fixed_fir.py", ROOT / "fpga/rtl/fixed_fir_iq.v"]
    env = {key: value for key, value in os.environ.items() if key.upper() in {"SYSTEMROOT", "WINDIR", "TEMP", "TMP", "COMSPEC"}}
    env["PATH"] = str(gcc.parent) + os.pathsep + str(Path(env.get("SYSTEMROOT", r"C:\Windows")) / "System32")
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "scope": "host_Windows_C99_execution_not_ARM_or_board", "arm_execution": False, "board_accessed": False, "hardware_throughput_measured": False, "compiler": str(gcc), "compiler_sha256": digest(gcc), "vector_root": str(vectors), "manifest_sha256": digest(vectors / "manifest.json"), "saved_reference_report_sha256": digest(vectors / "report.json"), "all_126_vector_files_verified_before_C_execution": True, "sources": [{"path": str(path), "sha256": digest(path)} for path in sources], "cases": [], "all_passed": False}
    try:
        version, _ = run([gcc, "--version"], env, output / "compiler-version.log")
        target, _ = run([gcc, "-dumpmachine"], env, output / "compiler-target.log")
        report["compiler_version"] = version.stdout.splitlines()[0]
        report["compiler_target"] = target.stdout.strip()
        executable = output / "fir_hex_cli.exe"
        command = [gcc, "-std=c99", "-O2", "-Wall", "-Wextra", "-Wpedantic", "-Wconversion", "-Wsign-conversion", "-Werror", "-static-libgcc", sources[1], sources[2], "-o", executable]
        report["compile_command"] = [str(x) for x in command]
        run(command, env, output / "compile.log")
        report["executable_sha256"] = digest(executable)
        for directory, case, loaded, verified in cases:
            process, elapsed = run([executable, directory/"coefficients.hex", directory/"input_i.hex", directory/"input_q.hex", "--reset-replay"], env, output/(case["name"] + ".csv"))
            rows = [line.split(",") for line in process.stdout.splitlines()]
            if len(rows) != 2*case["expected_output_count"] or any(len(row) != 6 or any(not re.fullmatch(r"-?\d+", value) for value in row) for row in rows):
                raise AssertionError("Malformed C output rows")
            actual = np.asarray(rows, dtype=np.int64)
            inputs = np.column_stack((loaded["input_i.hex"], loaded["input_q.hex"]))
            python_result = apply_fixed_fir_full(inputs, loaded["coefficients.hex"])
            expected = np.column_stack((loaded["expected_i.hex"], loaded["expected_q.hex"], loaded["saturated_i.hex"], loaded["saturated_q.hex"], python_result.accumulators))
            np.testing.assert_array_equal(python_result.counts, expected[:, :2])
            np.testing.assert_array_equal(python_result.saturated, expected[:, 2:4])
            for replay in range(2):
                np.testing.assert_array_equal(actual[replay*len(expected):(replay+1)*len(expected)], expected)
            result = {"name": case["name"], "passed": True, "complex_outputs_per_pass": len(expected), "passes": 2, "tail_samples_per_pass": case["tap_count"]-1, "saturated_i_per_pass": int(expected[:, 2].sum()), "saturated_q_per_pass": int(expected[:, 3].sum()), "accumulators_also_exact": True, "explicit_reset_replay_exact": True, "host_execution_seconds_not_ARM_throughput": elapsed, "verified_vector_files": verified, "csv_sha256": digest(output/(case["name"] + ".csv"))}
            report["cases"].append(result)
            print(f"PASS {case['name']} outputs={len(expected)} I/Q/flags/accumulators/reset", flush=True)
        rounding_values = [0, 65535, 65536, 65537, 196607, 196608, 196609, 327680, -65535, -65536, -65537, -196607, -196608, -196609, -327680, 32767*131072+65535, 32767*131072+65536, -32768*131072-65536, -32768*131072-65537, (1<<35)-1, -(1<<35)]
        for number, value in enumerate(rounding_values):
            process, _ = run([executable, "--quantize", value], env, output/f"rounding-{number:02d}.log")
            count, flag = (int(word) for word in process.stdout.strip().split(","))
            if (count, bool(flag)) != quantize_accumulator(value): raise AssertionError("Direct rounding boundary mismatch")
        report["direct_rounding_boundary_checks"] = len(rounding_values)
        rejected = []
        for label, coeff, i_data, q_data in [("input_high_bits", b"20000\n", b"1000\n", b"000\n"), ("extra_token", b"20000\n", b"001 002\n", b"000\n"), ("invalid_character", b"20000\n", b"00g\n", b"000\n"), ("embedded_nul", b"20000\n", b"001\x00002\n", b"000\n"), ("overlong_line", b"20000\n", b" "*129+b"001\n", b"000\n"), ("coefficient_high_bits", b"40000\n", b"001\n", b"000\n"), ("too_many_taps", b"00000\n"*64, b"001\n", b"000\n"), ("empty_coefficients", b"", b"001\n", b"000\n"), ("unequal_iq_lengths", b"20000\n", b"001\n002\n", b"000\n"), ("empty_input", b"20000\n", b"", b"")]:
            folder = output / "invalid-inputs" / label
            folder.mkdir(parents=True)
            for filename, data in [("coeff.hex", coeff), ("i.hex", i_data), ("q.hex", q_data)]: (folder/filename).write_bytes(data)
            process, _ = run([executable, folder/"coeff.hex", folder/"i.hex", folder/"q.hex"], env, folder/"rejection.log", allow_failure=True)
            if process.returncode == 0: raise AssertionError(f"Malformed input accepted: {label}")
            rejected.append({"case": label, "returncode": process.returncode})
        for value in [1<<35, -(1<<35)-1, -(1<<63)]:
            process, _ = run([executable, "--quantize", value], env, output/f"invalid-accumulator-{value}.log", allow_failure=True)
            if process.returncode == 0: raise AssertionError("Out-of-range accumulator accepted")
        report["invalid_hex_cases_rejected"] = rejected
        report["out_of_range_accumulators_rejected"] = 3
        report["case_count"] = len(report["cases"])
        report["complex_outputs_per_pass"] = sum(case["complex_outputs_per_pass"] for case in report["cases"])
        report["complex_outputs_including_reset_replay"] = 2 * report["complex_outputs_per_pass"]
        report["all_passed"] = True
        print(f"ALL {report['case_count']} C cases passed: {report['complex_outputs_per_pass']} outputs plus reset replay", flush=True)
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Evidence: {output}", flush=True)


if __name__ == "__main__":
    main()
