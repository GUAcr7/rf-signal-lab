"""Validate P36 runner locally; never call its main or open any serial handle."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

import p36_full_rx_run as runner

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-report", type=Path, required=True)
    args = parser.parse_args()
    output = ROOT / "results" / datetime.now(timezone.utc).strftime("p36-full-runner-check-%Y%m%dT%H%M%SZ")
    output.mkdir(exist_ok=False)
    source = ROOT / "experiments/p36_full_rx_run.py"
    test = ROOT / "tests/test_p36_full_rx_runner.py"
    dependencies = [ROOT / "experiments" / name for name in ["p32_session.py", "p35_uart_files.py", "p35_once_merged_trial.py"]]
    paths = [source, test, Path(__file__).resolve(), *dependencies]
    report = dict(schema="rfsig.full_rx_runner_offline_check.v1", status="started", serial_opened=False,
                  board_operations=False, inputs_sha256={str(path.relative_to(ROOT)): sha(path) for path in paths})
    for path in paths:
        (output / path.name).write_bytes(path.read_bytes())
    try:
        inputs = runner.load_build(args.build_report)
        report.update(build_report=str(inputs["path"]), build_report_sha256=inputs["report_sha256"],
                      binary_sha256=inputs["report"]["binary_sha256"], local_build_gate_passed=True)
        compile(source.read_text("utf-8"), str(source), "exec")
        report["python_syntax_valid"] = True
        argv = [sys.executable, "-m", "pytest", str(test), "-q", "--junitxml=" + str(output / "tests.xml")]
        report["test_argv"] = argv
        result = subprocess.run(argv, cwd=ROOT, capture_output=True, timeout=180)
        (output / "pytest.stdout").write_bytes(result.stdout)
        (output / "pytest.stderr").write_bytes(result.stderr)
        report["test_returncode"] = result.returncode
        if result.returncode:
            raise RuntimeError("runner tests failed")
        cases = list(ET.parse(output / "tests.xml").getroot().iter("testcase"))
        report["test_count"] = len(cases)
        if not cases or any(list(case.iter(tag)) for case in cases for tag in ["failure", "error", "skipped"]):
            raise RuntimeError("runner tests incomplete")
        report["inputs_unchanged"] = report["inputs_sha256"] == {str(path.relative_to(ROOT)): sha(path) for path in paths}
        if not report["inputs_unchanged"]:
            raise RuntimeError("runner inputs changed during check")
        report["status"] = "passed_offline_actual_C_metadata_and_fail_closed_runner_checks"
    except Exception as exc:
        report.update(status="failed", error=repr(exc))
        raise
    finally:
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(output)


if __name__ == "__main__":
    main()
