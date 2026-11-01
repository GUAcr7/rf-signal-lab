"""Compile and self-check the standalone FIR RTL against saved integer vectors."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from time import perf_counter


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TOOL = Path(r"E:\FPGA_Tools\IcarusVerilog13.0\ucrt64")


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check_case(vector_root, entry):
    directory = (vector_root / entry["directory"]).resolve()
    if not directory.is_relative_to(vector_root):
        raise ValueError("vector directory escapes manifest root")
    case = json.loads((directory / "case.json").read_text(encoding="utf-8"))
    for key in ("name", "input_count", "tap_count", "expected_output_count"):
        if case[key] != entry[key]:
            raise ValueError(f"case and manifest disagree: {key}")
    if (case["input_bits"], case["coefficient_bits"], case["coefficient_fractional_bits"],
            case["accumulator_bits"], case["output_bits"]) != (12, 18, 17, 36, 16):
        raise ValueError("unsupported fixed-point contract")
    if not 1 <= case["tap_count"] <= 63:
        raise ValueError("unsupported tap count")
    if case["expected_output_count"] != case["input_count"] + case["tap_count"] - 1:
        raise ValueError("full-convolution tail length mismatch")
    verified = []
    for spec in case["files"]:
        path = (directory / spec["name"]).resolve()
        if not path.is_relative_to(directory) or sha256(path) != spec["sha256"]:
            raise ValueError(f"missing/modified vector: {spec['name']}")
        words = path.read_text(encoding="ascii").splitlines()
        if len(words) != spec["words"] or any(
                not re.fullmatch(r"[0-9a-fA-F]+", word) or int(word, 16) >= 1 << spec["bits"]
                for word in words):
            raise ValueError(f"invalid vector word count/range: {spec['name']}")
        verified.append({"name": spec["name"], "sha256": spec["sha256"], "words": len(words)})
    return directory, case, verified


def execute(command, *, cwd, env, logfile, timeout):
    started = perf_counter()
    completed = subprocess.run([str(x) for x in command], cwd=cwd, env=env,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, encoding="utf-8", errors="replace", timeout=timeout)
    logfile.write_text(completed.stdout, encoding="utf-8")
    if completed.returncode != 0:
        raise RuntimeError(f"command failed ({completed.returncode}); see {logfile}")
    return completed.stdout, perf_counter()-started


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("vectors", type=Path)
    parser.add_argument("--tool-root", type=Path, default=DEFAULT_TOOL)
    parser.add_argument("--case", action="append", default=[])
    parser.add_argument("--no-stalls", action="store_true", help="Exercise uninterrupted source and sink handshakes")
    parser.add_argument("--default-coeff", action="store_true", help="Exercise the RTL production coefficient-file initialization")
    args = parser.parse_args()
    vector_root, tool = args.vectors.resolve(), args.tool_root.resolve()
    manifest_path = vector_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = [entry for entry in manifest["cases"] if not args.case or entry["name"] in args.case]
    if not entries or set(args.case)-{entry["name"] for entry in entries}:
        raise ValueError("unknown or empty case selection")
    for executable in (tool/"bin/iverilog.exe", tool/"bin/vvp.exe"):
        if not executable.is_file():
            raise FileNotFoundError(executable)
    rtl, bench = ROOT/"fpga/rtl/fixed_fir_iq.v", ROOT/"fpga/tb/tb_fixed_fir_iq.sv"
    default_coeff = ROOT/"fpga/ip/fir63_q17.hex"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = ROOT/"results"/f"p07-fir-rtl-{stamp}"
    output.mkdir()
    env = os.environ.copy()
    env["PATH"] = str(tool/"bin") + os.pathsep + r"C:\msys64\ucrt64\bin" + os.pathsep + env.get("PATH", "")
    report = {"checked_at": datetime.now(timezone.utc).isoformat(),
              "scope": "standalone_RTL_simulation_not_Vivado_synthesis_or_board_execution",
              "input_sample_rate_assumption_hz": 1_000_000,
              "clock_period_ns_in_simulation": 10,
              "timing_closed": False, "hardware_resources_measured": False,
              "random_stalls_enabled": not args.no_stalls,
              "default_coefficient_initialization": args.default_coeff,
              "vector_manifest": str(manifest_path), "vector_manifest_sha256": sha256(manifest_path),
              "sources": [{"path": str(path), "sha256": sha256(path)} for path in (rtl, bench, default_coeff)],
              "tool_root": str(tool), "cases": [], "all_passed": False}
    try:
        version, _ = execute([tool/"bin/iverilog.exe", "-B", tool/"lib/ivl", "-V"],
                             cwd=ROOT, env=env, logfile=output/"tool-version.log", timeout=30)
        report["tool_version_first_line"] = version.splitlines()[0]
        compiled = {}
        for entry in entries:
            directory, case, verified = check_case(vector_root, entry)
            count = case["tap_count"]
            if args.default_coeff and (count != 63 or sha256(directory/"coefficients.hex") != sha256(default_coeff)):
                raise ValueError("default-coeff mode requires the official 63-tap coefficient vector")
            if count not in compiled:
                image = output/f"fir-{count}.vvp"
                compile_output, elapsed = execute(
                    [tool/"bin/iverilog.exe", "-B", tool/"lib/ivl", "-g2012", "-Wall",
                     "-s", "tb_fixed_fir_iq", "-P", f"tb_fixed_fir_iq.N_TAPS={count}",
                     "-P", f"tb_fixed_fir_iq.RANDOM_STALLS={int(not args.no_stalls)}",
                     "-P", f"tb_fixed_fir_iq.USE_DEFAULT_COEFF={int(args.default_coeff)}",
                     "-o", image, rtl, bench], cwd=ROOT, env=env,
                    logfile=output/f"compile-{count}.log", timeout=30)
                if compile_output.strip():
                    raise RuntimeError("unexpected compilation diagnostic; inspect compile log")
                compiled[count] = image
            arguments = {"CASE": case["name"], "INPUT_COUNT": case["input_count"],
                         "OUTPUT_COUNT": case["expected_output_count"],
                         "I": directory/"input_i.hex", "Q": directory/"input_q.hex",
                         "EI": directory/"expected_i.hex", "EQ": directory/"expected_q.hex",
                         "SI": directory/"saturated_i.hex", "SQ": directory/"saturated_q.hex",
                         "COEFF": directory/"coefficients.hex"}
            text, seconds = execute([tool/"bin/vvp.exe", "-M", tool/"lib/ivl", compiled[count],
                                     *[f"+{key}={value}" for key, value in arguments.items()]],
                                    cwd=ROOT, env=env, logfile=output/(case["name"]+".log"), timeout=120)
            lines = [line for line in text.splitlines() if line.startswith("PASS case=")]
            if len(lines) != 1 or "WARNING" in text or "ERROR" in text or "FATAL" in text:
                raise AssertionError(f"missing clean self-check for {case['name']}")
            metrics = dict(re.findall(r"(\w+)=([^ ]+)", lines[0]))
            if (int(metrics["accepted"]) != case["expected_output_count"] or
                    int(metrics["received"]) != case["expected_output_count"] or
                    int(metrics["valid_after_cycles"]) != count+1 or
                    int(metrics["handshake_min"]) < count+2 or
                    int(metrics["reset_during_mac"]) != 1 or int(metrics["reset_stalled_output"]) != 1 or
                    int(metrics["rounding_checks"]) != 22 or
                    int(metrics["random_stalls"]) != int(not args.no_stalls) or
                    int(metrics["default_coeff"]) != int(args.default_coeff)):
                raise AssertionError("invalid self-check counters")
            report["cases"].append({"name": case["name"], "passed": True,
                                     "sample_comparisons": case["expected_output_count"],
                                     "metrics": metrics, "host_simulation_seconds": seconds,
                                     "verified_vector_files": verified})
            print(lines[0], flush=True)
        report["all_passed"] = True
        report["case_count"] = len(report["cases"])
        report["sample_comparisons"] = sum(x["sample_comparisons"] for x in report["cases"])
        print(f"All {report['case_count']} RTL cases passed, {report['sample_comparisons']} complex outputs.", flush=True)
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        (output/"report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Evidence: {output}", flush=True)


if __name__ == "__main__":
    main()
