"""Offline C mock tests and ARM cross-build only. Never open a board/serial port."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
TOOL = Path("E:/FPGA_Tools/ARM-GNU-A-8.3-2019.03/attempt-2/gcc-arm-8.3-2019.03-x86_64-arm-linux-gnueabihf/bin")


def posix(path):
    value = Path(path).resolve().as_posix()
    return "/mnt/" + value[0].lower() + value[2:]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    output = ROOT / "results" / datetime.now(timezone.utc).strftime("p36-full-rx-build-%Y%m%dT%H%M%SZ")
    output.mkdir(exist_ok=False)
    source = ROOT / "embedded/arm_rx_full_p36/arm_rx_full_p36.c"
    header = ROOT / "embedded/vendor/libiio-v0.24/iio.h"
    provenance = header.parent / "source.json"
    test = ROOT / "tests/test_native_rx_full_p36.py"
    mock = ROOT / "tests/native/mock_rx_full_p36.c"
    inputs = [source, header, provenance, test, mock, Path(__file__).resolve()]
    hashes = {str(path.relative_to(ROOT)): sha(path) for path in inputs}
    for path in inputs:
        (output / path.name).write_bytes(path.read_bytes())
    report = {
        "schema": "rfsig.full_rx_build.v1", "status": "started", "inputs_sha256": hashes,
        "source": str(source), "source_sha256": sha(source),
        "runtime_libiio_required": "0.20", "runtime_receiver_glibc": "2.23",
        "default_blocks": 16, "maximum_blocks": 64, "frames_per_buffer": 65536,
        "frame_bytes": 4, "RF_attributes_written": False, "TX_API_loaded": False,
        "board_execution": "not_attempted", "complete_stream_saved": False,
        "lossless_proven": False, "known_target_proven": False,
        "evidence_scope": "host_actual_C_mock_tests_and_ARM_ELF_only",
    }

    def execute(label, arguments, timeout):
        report[label + "_argv"] = arguments
        try:
            result = subprocess.run(arguments, cwd=ROOT, capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            (output / (label + ".stdout")).write_bytes(exc.stdout or b"")
            (output / (label + ".stderr")).write_bytes(exc.stderr or b"")
            raise RuntimeError(label + " timeout") from exc
        (output / (label + ".stdout")).write_bytes(result.stdout)
        (output / (label + ".stderr")).write_bytes(result.stderr)
        report[label + "_returncode"] = result.returncode
        if result.returncode:
            raise RuntimeError(label + " failed: " + result.stderr.decode(errors="replace")[-2000:])
        return result

    try:
        metadata = json.loads(provenance.read_text("utf-8-sig"))
        report["header"] = metadata
        if sha(header) != metadata["sha256"]:
            raise RuntimeError("pinned libiio header changed")
        junit = output / "host-tests.xml"
        execute("host_tests", [sys.executable, "-m", "pytest", str(test), "-q", "--junitxml=" + str(junit)], 180)
        suites = ET.parse(junit).getroot()
        cases = list(suites.iter("testcase"))
        report["host_test_count"] = len(cases)
        report["host_tests_have_no_failures_errors_or_skips"] = bool(cases) and not any(
            list(case.iter("failure")) or list(case.iter("error")) or list(case.iter("skipped")) for case in cases)
        if not report["host_tests_have_no_failures_errors_or_skips"]:
            raise RuntimeError("host test coverage incomplete")
        execute("compiler_version", ["wsl.exe", "--exec", posix(TOOL / "arm-linux-gnueabihf-gcc"), "--version"], 20)
        binary = output / "arm-rx-full-p36"
        execute("compile", [
            "wsl.exe", "--exec", posix(TOOL / "arm-linux-gnueabihf-gcc"),
            "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
            "-mcpu=cortex-a9", "-mfpu=neon", "-mfloat-abi=hard", "-marm", "-pthread",
            "-I", posix(header.parent), posix(source), "-o", posix(binary), "-ldl", "-lrt",
        ], 90)
        elf = execute("readelf", ["wsl.exe", "--exec", posix(TOOL / "arm-linux-gnueabihf-readelf"), "-h", "-A", "-l", "-V", "-d", posix(binary)], 20)
        text = elf.stdout.decode(errors="replace")
        glibc = sorted({tuple(map(int, version.split("."))) for version in re.findall(r"GLIBC_([0-9]+(?:\.[0-9]+)+)", text)})
        checks = {
            "ELF32": "ELF32" in text,
            "little_endian": "little endian" in text,
            "ARM": "Machine:                           ARM" in text,
            "hard_float_calling_convention": "VFP registers" in text,
            "armhf_interpreter": "/lib/ld-linux-armhf.so.3" in text,
            "pthread_linked": "libpthread.so.0" in text,
            "required_glibc_not_newer_than_receiver": bool(glibc) and max(glibc) <= (2, 23),
            "inputs_unchanged_during_build": hashes == {str(path.relative_to(ROOT)): sha(path) for path in inputs},
        }
        report.update({"binary": str(binary), "binary_sha256": sha(binary), "binary_bytes": binary.stat().st_size,
                       "required_glibc_versions": [".".join(map(str, version)) for version in glibc], "target_checks": checks})
        if not all(checks.values()):
            raise RuntimeError("target/input verification failed: " + repr(checks))
        report["status"] = "offline_mock_tests_and_cross_compile_verified"
    except Exception as exc:
        report.update({"status": "failed", "error": str(exc)})
        raise
    finally:
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(output)


if __name__ == "__main__":
    main()
