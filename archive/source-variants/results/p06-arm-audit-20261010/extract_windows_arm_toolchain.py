"""Extract only the 2021.1 Windows ARM Linux toolchain into a new directory.

Uses the existing Windows tar reader for the SFD's 7z payload files. Never
invokes xsetup or changes PATH. No target ARM binary is executed by this script.
"""
from pathlib import Path, PurePosixPath
from datetime import datetime, timezone
import hashlib
import json
import subprocess

HERE = Path(__file__).resolve().parent
SFD = Path(r"E:\FPGA_Tools\Installers\Vivado2021.1\Xilinx_Unified_2021.1_0610_2318")
TARGET = Path(r"E:\FPGA_Tools\ARM-GNU-2021.1")
PREFIX = "gnu/aarch32/nt/gcc-arm-linux-gnueabi/"
TAR = Path(r"C:\Windows\System32\tar.exe")


def digest(path, algorithm="sha256"):
    h = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def safe_name(name):
    p = PurePosixPath(name)
    return (name.startswith(PREFIX) and not p.is_absolute()
            and ".." not in p.parts and ":" not in name
            and "\n" not in name and "\r" not in name)


def main():
    if TARGET.exists():
        raise RuntimeError(f"Refusing to overwrite an existing target: {TARGET}")
    expected = json.loads((HERE / "sfd-windows-arm-linux-files.json").read_text(encoding="utf-8"))
    by_payload = {}
    names = set()
    for entry in expected:
        if not safe_name(entry["path"]) or entry["path"] in names:
            raise RuntimeError("Invalid or duplicate manifest path")
        names.add(entry["path"])
        by_payload.setdefault(entry["payload"], []).append(entry)
    report = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_root": str(SFD), "target_root": str(TARGET),
        "selected_prefix": PREFIX, "expected_files": len(expected),
        "expected_bytes": sum(e["bytes"] for e in expected),
        "payloads": [], "scope": "New directory only; no installer, system PATH or board operation",
    }
    directory_names = set()
    for filename, entries in sorted(by_payload.items()):
        payload = SFD / "payload" / filename
        source_stat = payload.stat()
        result = subprocess.run([str(TAR), "-tvf", str(payload)], capture_output=True, text=True, encoding="utf-8", errors="replace")
        if result.returncode:
            raise RuntimeError(f"Cannot list {filename}: {result.stderr}")
        # verbose libarchive format starts with a file type. A selected symlink
        # could redirect subsequent writes, so disallow links and special files.
        matched = [line for line in result.stdout.splitlines() if PREFIX in line]
        if any(not line.startswith(("-", "d")) for line in matched):
            raise RuntimeError(f"Nonregular selected member in {filename}")
        listed = subprocess.run([str(TAR), "-tf", str(payload)], capture_output=True, text=True, encoding="utf-8", errors="replace", check=True).stdout.splitlines()
        actual = {name for name in listed if name.startswith(PREFIX) and not name.endswith("/")}
        directories = {name.rstrip("/") for name in listed if name.startswith(PREFIX) and name.endswith("/")}
        expected_names = {e["path"] for e in entries}
        directory_entries = expected_names & directories
        if actual != expected_names - directory_entries or any(not safe_name(name) for name in actual):
            raise RuntimeError(f"Manifest/member set differs: {filename}")
        directory_names.update(directory_entries)
        allowlist = HERE / (filename + ".allowlist.txt")
        allowlist.write_text("\n".join(sorted(actual)) + "\n", encoding="utf-8")
        report["payloads"].append({"path": str(payload), "bytes": source_stat.st_size,
            "sha256": digest(payload), "selected_files": len(entries),
            "allowlist": str(allowlist), "source_mtime_ns": source_stat.st_mtime_ns})
    TARGET.mkdir()  # Deliberately fail if another process created the target.
    for source in report["payloads"]:
        result = subprocess.run([str(TAR), "--no-same-owner", "--no-same-permissions", "-xf", source["path"], "-C", str(TARGET), "-T", source["allowlist"]], capture_output=True, text=True, encoding="utf-8", errors="replace")
        source["extraction_exit_code"] = result.returncode
        source["extraction_stderr"] = result.stderr
        print("extracted", Path(source["path"]).name, result.returncode, flush=True)
        (HERE / "toolchain-extraction.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        if result.returncode:
            raise RuntimeError("Extraction failed; retain the partial target for inspection.")
    for name in directory_names:
        (TARGET / Path(name)).mkdir(parents=True, exist_ok=True)
    report["explicit_empty_directory_entries"] = sorted(directory_names)
    report["expected_regular_files"] = len(expected) - len(directory_names)
    checked = []
    for entry in expected:
        path = TARGET / Path(entry["path"])
        if not path.resolve().is_relative_to(TARGET.resolve()) or path.is_symlink():
            raise RuntimeError("Extracted path is not confined")
        if entry["path"] in directory_names:
            checked.append({"path": entry["path"], "kind": "directory", "manifest_match": path.is_dir() and entry["bytes"] == 0})
            continue
        md5 = digest(path, "md5")
        match = path.stat().st_size == entry["bytes"] and md5 == entry["archive_declared_md5"]
        checked.append({"path": entry["path"], "bytes": path.stat().st_size, "md5": md5, "manifest_match": match})
    report["all_expected_files_size_md5_match"] = all(e["manifest_match"] for e in checked)
    report["actual_files"] = len([p for p in TARGET.rglob("*") if p.is_file()])
    report["no_extra_files"] = report["actual_files"] == report["expected_regular_files"]
    report["payload_source_stats_unchanged"] = all(Path(e["path"]).stat().st_size == e["bytes"] and Path(e["path"]).stat().st_mtime_ns == e["source_mtime_ns"] for e in report["payloads"])
    report["script_sha256"] = digest(Path(__file__))
    (HERE / "toolchain-extracted-file-checks.json").write_text(json.dumps(checked, indent=2), encoding="utf-8")
    (HERE / "toolchain-extraction.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("actual_files", "all_expected_files_size_md5_match", "no_extra_files", "payload_source_stats_unchanged")}), flush=True)
    if not (report["all_expected_files_size_md5_match"] and report["no_extra_files"] and report["payload_source_stats_unchanged"]):
        raise RuntimeError("Final verification failed")


if __name__ == "__main__":
    main()
