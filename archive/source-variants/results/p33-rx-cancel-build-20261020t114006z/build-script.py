"""Cross-build a bounded RX cancel/recreate diagnostic; never access a board."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

from p22_acquire_comparison import ROOT

TOOL = Path("E:/FPGA_Tools/ARM-GNU-A-8.3-2019.03/attempt-2/gcc-arm-8.3-2019.03-x86_64-arm-linux-gnueabihf/bin")


def posix(path):
    value = Path(path).resolve().as_posix()
    return "/mnt/" + value[0].lower() + value[2:]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    output = ROOT / "results" / datetime.now(timezone.utc).strftime("p33-rx-cancel-build-%Y%m%dT%H%M%SZ")
    output.mkdir(exist_ok=False)
    source = ROOT / "embedded/arm_rx_cancel/arm_rx_cancel.c"
    header = ROOT / "embedded/vendor/libiio-v0.24/iio.h"
    metadata_path = header.parent / "source.json"
    metadata = json.loads(metadata_path.read_text("utf-8-sig"))
    if sha(header) != metadata["sha256"]:
        raise RuntimeError("pinned libiio header changed")
    binary = output / "arm-rx-cancel"
    arguments = [
        "wsl.exe", "--exec", posix(TOOL / "arm-linux-gnueabihf-gcc"),
        "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
        "-mcpu=cortex-a9", "-mfpu=neon", "-mfloat-abi=hard", "-marm",
        "-pthread", "-I", posix(header.parent), posix(source),
        "-o", posix(binary), "-ldl", "-lrt",
    ]
    # Exact inputs are copied before execution, including failures.
    (output / "source.c").write_bytes(source.read_bytes())
    (output / "iio.h").write_bytes(header.read_bytes())
    (output / "header-source.json").write_bytes(metadata_path.read_bytes())
    (output / "build-script.py").write_bytes(Path(__file__).read_bytes())
    result = subprocess.run(arguments, capture_output=True, timeout=90)
    (output / "compile.stdout").write_bytes(result.stdout)
    (output / "compile.stderr").write_bytes(result.stderr)
    base = {
        "schema": "rfsig.rx_cancel_build.v1", "source": str(source),
        "source_sha256": sha(source), "header_sha256": sha(header),
        "header_metadata_sha256": sha(metadata_path), "header": metadata,
        "compiler_argv": arguments, "compile_returncode": result.returncode,
        "runtime_libiio_required": "0.20", "RF_attributes_written": False,
        "TX_API_loaded": False, "board_execution": "pending",
        "known_target_proven": False, "lossless_proven": False,
    }
    if result.returncode:
        base["status"] = "compile_failed"
        (output / "report.json").write_text(json.dumps(base, indent=2) + "\n", encoding="utf-8")
        raise RuntimeError(result.stderr.decode(errors="replace"))
    readelf_argv = ["wsl.exe", "--exec", posix(TOOL / "arm-linux-gnueabihf-readelf"), "-h", "-A", "-l", "-V", "-d", posix(binary)]
    elf = subprocess.run(readelf_argv, capture_output=True, timeout=20)
    (output / "elf.txt").write_bytes(elf.stdout)
    (output / "elf.stderr").write_bytes(elf.stderr)
    text = elf.stdout.decode("utf-8", errors="replace")
    checks = {
        "readelf_success": elf.returncode == 0,
        "ELF32": "ELF32" in text,
        "little_endian": "little endian" in text,
        "ARM": "Machine:                           ARM" in text,
        "hard_float_calling_convention": "VFP registers" in text,
        "armhf_interpreter": "/lib/ld-linux-armhf.so.3" in text,
        "pthread_linked": "libpthread.so.0" in text,
    }
    base.update({"status": "cross_compile_verified" if all(checks.values()) else "target_verification_failed",
                 "binary": str(binary), "binary_sha256": sha(binary),
                 "binary_bytes": binary.stat().st_size, "target_checks": checks,
                 "readelf_argv": readelf_argv, "readelf_returncode": elf.returncode})
    (output / "report.json").write_text(json.dumps(base, indent=2) + "\n", encoding="utf-8")
    if not all(checks.values()):
        raise RuntimeError("unexpected ELF target: " + repr(checks))
    print(output)


if __name__ == "__main__":
    main()
