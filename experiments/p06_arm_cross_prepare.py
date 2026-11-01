"""Validate official archive, isolate a WSL toolchain, and cross-compile only.

No board connection, privileged installation, PATH edits, or target execution.
The resulting report distinguishes host checks from pending ARM execution.
"""
from __future__ import annotations

import hashlib
import argparse
import json
import posixpath
import shutil
import subprocess
import tarfile
from datetime import datetime, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
OUT = PROJECT / "results/p06-arm-cross-20261011"
BASE = Path("E:/FPGA_Tools/ARM-GNU-A-8.3-2019.03")
EXTRACT_BASE = BASE
NAME = "gcc-arm-8.3-2019.03-x86_64-arm-linux-gnueabihf"
ARCHIVE = BASE / (NAME + ".tar.xz")
EXPECTED_MD5 = "650dc30f7e937fa12e37ea70ff6e10dd"
DISTRO = "Ubuntu-24.04"
report: dict = {
    "started_at_utc": datetime.now(timezone.utc).isoformat(),
    "scope": "Official toolchain validation and cross-compilation; no target execution",
    "board_execution": "pending", "live_board_libc_compatibility": "pending",
    "commands": [],
}


def digest(path: Path, kind: str = "sha256") -> str:
    h = hashlib.new(kind)
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def wsl_path(path: Path) -> str:
    resolved = path.resolve().as_posix()
    if len(resolved) < 3 or resolved[1:3] != ":/":
        raise ValueError("Expected a Windows drive path")
    return "/mnt/" + resolved[0].lower() + resolved[2:]


def decode(data: bytes) -> str:
    return data.decode("utf-16-le" if b"\x00" in data[:100] else "utf-8", errors="replace")


def run(label: str, argv: list[str], *, linux: bool = True, timeout: int = 180) -> str:
    command = ["wsl.exe", "-d", DISTRO, "--exec", *argv] if linux else argv
    try:
        p = subprocess.run(command, capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        (OUT / (label + ".stdout.txt")).write_text(decode(exc.stdout or b""), encoding="utf-8")
        (OUT / (label + ".stderr.txt")).write_text(decode(exc.stderr or b""), encoding="utf-8")
        report["commands"].append({"label": label, "argv": command, "exit_code": None,
                                   "timed_out_seconds": timeout})
        raise
    stdout, stderr = decode(p.stdout), decode(p.stderr)
    (OUT / (label + ".stdout.txt")).write_text(stdout, encoding="utf-8")
    (OUT / (label + ".stderr.txt")).write_text(stderr, encoding="utf-8")
    report["commands"].append({"label": label, "argv": command, "exit_code": p.returncode})
    if p.returncode != 0:
        raise RuntimeError(f"{label} exited {p.returncode}; inspect saved diagnostics")
    return stdout


def validate_archive() -> None:
    if not ARCHIVE.is_file() or (EXTRACT_BASE / NAME).exists():
        raise RuntimeError("Missing archive or extraction root already exists; refusing overwrite")
    published = (BASE / "published-md5.asc").read_text(encoding="utf-8").split()
    if published != [EXPECTED_MD5, ARCHIVE.name]:
        raise RuntimeError("Unexpected published checksum text")
    actual = digest(ARCHIVE, "md5")
    if actual != EXPECTED_MD5:
        raise RuntimeError("Archive MD5 mismatch; may still be downloading")
    report["archive"] = {"path": str(ARCHIVE), "bytes": ARCHIVE.stat().st_size,
                         "published_md5": EXPECTED_MD5, "actual_md5": actual,
                         "sha256": digest(ARCHIVE), "checksum_kind": "MD5, not a signature"}
    inventory = []
    names: dict[str, tarfile.TarInfo] = {}
    total = 0
    with tarfile.open(ARCHIVE, "r:xz") as tar:
        for member in tar:
            name = posixpath.normpath(member.name)
            if ("\\" in member.name or member.name.startswith("/") or
                    name != NAME and not name.startswith(NAME + "/") or
                    any(part == ".." for part in member.name.split("/"))):
                raise RuntimeError(f"Unsafe archive member: {member.name}")
            if name in names or not (member.isfile() or member.isdir() or member.issym() or member.islnk()):
                raise RuntimeError(f"Duplicate or unsupported member: {name}")
            if member.mode & 0o6000:
                raise RuntimeError(f"Privileged mode rejected: {name}")
            target = None
            if member.issym() or member.islnk():
                if member.linkname.startswith("/") or "\\" in member.linkname:
                    raise RuntimeError(f"Absolute/invalid link: {name}")
                target = posixpath.normpath(posixpath.join(posixpath.dirname(name), member.linkname)
                                          if member.issym() else member.linkname)
                if target != NAME and not target.startswith(NAME + "/"):
                    raise RuntimeError(f"Link escapes root: {name}")
            names[name] = member
            total += member.size
            inventory.append({"path": name, "size": member.size, "mode": oct(member.mode),
                              "kind": member.type.decode("ascii"), "link_target": target})
        for name in names:
            parent = posixpath.dirname(name)
            while parent.startswith(NAME + "/"):
                if parent in names and (names[parent].issym() or names[parent].islnk()):
                    raise RuntimeError(f"Member under linked parent rejected: {name}")
                parent = posixpath.dirname(parent)
    if total > 4 * 1024**3:
        raise RuntimeError("Unexpected extraction size")
    (OUT / "archive-members.json").write_text(json.dumps(inventory, indent=2), encoding="utf-8")
    report["archive_validation"] = {"members": len(names), "unpacked_bytes": total, "passed": True}


def main() -> None:
    if OUT.exists():
        raise RuntimeError("Evidence directory exists; preserve it rather than overwrite")
    OUT.mkdir(parents=True)
    shutil.copy2(Path(__file__), OUT / Path(__file__).name)
    try:
        validate_archive()
        run("host-uname", ["uname", "-a"])
        run("host-glibc", ["getconf", "GNU_LIBC_VERSION"])
        if EXTRACT_BASE != BASE:
            EXTRACT_BASE.mkdir(exist_ok=False)
        # WSL access to thousands of files on NTFS is much slower than ext4.
        # A bounded long-lived process is monitored asynchronously by the caller.
        run("extract", ["tar", "--extract", "--xz", "--no-same-owner", "--no-same-permissions",
                        "--file", wsl_path(ARCHIVE), "--directory", wsl_path(EXTRACT_BASE)], timeout=1200)
        prefix = wsl_path(EXTRACT_BASE / NAME / "bin/arm-linux-gnueabihf-")
        gcc, readelf = prefix + "gcc", prefix + "readelf"
        report["compiler_version"] = run("compiler-version", [gcc, "--version"])
        target = run("compiler-target", [gcc, "-dumpmachine"]).strip()
        if target != "arm-linux-gnueabihf":
            raise RuntimeError("Unexpected compiler target")
        report["compiler_target"] = target
        report["compiler_sysroot"] = run("compiler-sysroot", [gcc, "-print-sysroot"]).strip()
        sources = OUT / "sources"
        artifacts = OUT / "artifacts"
        sources.mkdir()
        artifacts.mkdir()
        for name in ["fixed_fir.h", "fixed_fir.c", "fir_hex_cli.c", "arm_smoke.c"]:
            shutil.copy2(PROJECT / "embedded/fir_reference" / name, sources / name)
        (sources / "hello.c").write_text('#include <stdio.h>\nint main(void) { puts("ARM_HELLO_PASS"); return 0; }\n', encoding="ascii")
        flags = ["-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-mcpu=cortex-a9",
                 "-mfpu=neon", "-mfloat-abi=hard", "-marm"]
        report["artifacts"] = []
        for name, source_names in [("hello", ["hello.c"]), ("fir-smoke", ["arm_smoke.c", "fixed_fir.c"]),
                                   ("fir-hex-cli", ["fir_hex_cli.c", "fixed_fir.c"])]:
            artifact = artifacts / name
            run("compile-" + name, [gcc, *flags, *[wsl_path(sources / s) for s in source_names], "-o", wsl_path(artifact)])
            header = run("elf-" + name, [readelf, "-h", "-A", "-l", "-d", "-V", wsl_path(artifact)])
            data = artifact.read_bytes()
            if (data[:6] != b"\x7fELF\x01\x01" or int.from_bytes(data[18:20], "little") != 40 or
                    "hard-float ABI" not in header or "/lib/ld-linux-armhf.so.3" not in header):
                raise RuntimeError("Unexpected ELF class/machine/ABI/loader")
            report["artifacts"].append({"name": name, "bytes": len(data), "sha256": digest(artifact),
                                        "ELF32_little_endian_ARM_hardfloat": True, "target_execution": "pending"})
        report["source_hashes"] = {p.name: digest(p) for p in sources.iterdir()}
        report["cross_compilation"] = "passed"
        report["status"] = "cross_compile_passed_target_run_pending"
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = str(exc)
        raise
    finally:
        report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        (OUT / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retry-extraction", action="store_true",
                        help="Preserve failed first attempt and use a new attempt-2 directory")
    args = parser.parse_args()
    if args.retry_extraction:
        OUT = PROJECT / "results/p06-arm-cross-20261011b"
        EXTRACT_BASE = BASE / "attempt-2"
        report["previous_attempt"] = "results/p06-arm-cross-20261011/report.json"
        report["previous_partial_extraction_used"] = False
    main()
