"""Package verified ARM executables and existing golden vectors; do not run on board."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import re
import shutil
import sys
import zipfile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from rfsig.fixed_fir import apply_fixed_fir_full
from p07_fir_c_check import verify_case

CROSS = ROOT / "results/p06-arm-cross-20261011b"
OUT = ROOT / "results/p07-arm-board-bundle-20261011"
VECTORS = ROOT / "results/p07-fixed-fir-20261010T080230137429Z"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    cross = json.loads((CROSS / "report.json").read_text())
    if cross.get("status") != "cross_compile_passed_target_run_pending":
        raise RuntimeError("Cross compilation has not passed")
    if OUT.exists():
        raise RuntimeError("Existing bundle retained; refusing overwrite")
    original = json.loads((VECTORS / "report.json").read_text())
    manifest = json.loads((VECTORS / "manifest.json").read_text())
    if sha(ROOT / "src/rfsig/fixed_fir.py") != original["code_sha256"]["src/rfsig/fixed_fir.py"]:
        raise RuntimeError("Golden arithmetic source changed")
    OUT.mkdir()
    bundle = OUT / "arm-fir-check"
    (bundle / "bin").mkdir(parents=True)
    (bundle / "vectors").mkdir()
    (bundle / "expected").mkdir()
    cases = []
    shell = ["#!/bin/sh", "set -eu", 'cd "$(dirname "$0")"',
             '[ "$(uname -m)" = armv7l ] || { echo "Expected ARMv7 Linux" >&2; exit 1; }',
             '[ -e /lib/ld-linux-armhf.so.3 ] || { echo "ARM hardfloat loader missing" >&2; exit 1; }',
             'command -v sha256sum >/dev/null', 'command -v cmp >/dev/null',
             'sha256sum -c SHA256SUMS',
             '[ ! -e outputs ] || { echo "Existing outputs retained; use a fresh bundle directory" >&2; exit 1; }',
             'mkdir outputs', 'uname -a > outputs/uname.txt',
             './bin/hello > outputs/hello.txt', 'cat outputs/hello.txt',
             './bin/fir-smoke > outputs/fir-smoke.txt', 'cat outputs/fir-smoke.txt']
    for item in cross["artifacts"]:
        source = CROSS / "artifacts" / item["name"]
        if sha(source) != item["sha256"]:
            raise RuntimeError("ARM artifact changed")
        shutil.copy2(source, bundle / "bin" / item["name"])
    shutil.copytree(CROSS / "sources", bundle / "sources")
    for entry, original_case in zip(manifest["cases"], original["cases"], strict=True):
        name = entry["name"]
        if not re.fullmatch(r"[a-z0-9_]+", name):
            raise RuntimeError("Unsafe case name")
        _, _, loaded, _ = verify_case(VECTORS, entry, original_case)
        reference = apply_fixed_fir_full(np.column_stack((loaded["input_i.hex"], loaded["input_q.hex"])), loaded["coefficients.hex"])
        expected = np.column_stack((loaded["expected_i.hex"], loaded["expected_q.hex"],
                                    loaded["saturated_i.hex"], loaded["saturated_q.hex"], reference.accumulators))
        np.testing.assert_array_equal(reference.counts, expected[:, :2])
        np.testing.assert_array_equal(reference.saturated, expected[:, 2:4])
        case_dir = bundle / "vectors" / name
        case_dir.mkdir()
        for filename in ("coefficients.hex", "input_i.hex", "input_q.hex"):
            shutil.copy2(VECTORS / entry["directory"] / filename, case_dir / filename)
        expected_path = bundle / "expected" / (name + ".csv")
        with expected_path.open("w", encoding="ascii", newline="\n") as f:
            np.savetxt(f, np.tile(expected, (2, 1)), delimiter=",", fmt="%d")
        shell.extend([f'./bin/fir-hex-cli vectors/{name}/coefficients.hex vectors/{name}/input_i.hex vectors/{name}/input_q.hex --reset-replay > outputs/{name}.csv',
                      f'cmp outputs/{name}.csv expected/{name}.csv', f'echo "ARM_CASE_PASS {name}"'])
        cases.append({"name": name, "outputs_including_reset_replay": 2 * len(expected), "expected_sha256": sha(expected_path)})
    shell.append(f'echo "ARM_FIR_ALL_PASS cases={len(cases)} outputs={sum(c["outputs_including_reset_replay"] for c in cases)}"')
    shell.append('echo "No RF, IIO, FPGA, boot or persistent-storage operations were performed."')
    (bundle / "run-on-board.sh").write_text("\n".join(shell) + "\n", encoding="ascii", newline="\n")
    (bundle / "README.txt").write_text(
        "ARMv7 Linux hardfloat FIR validation bundle. Not yet run on the board.\n"
        "First confirm the live board identity, libc and executable temporary mount.\n"
        "Transfer the whole directory into a new temporary board directory.\n"
        "Confirm SHA256SUMS before chmod. Then: chmod u+x bin/*; sh ./run-on-board.sh\n"
        "Expected success: ARM_HELLO_PASS, ARM_FIR_SMOKE_PASS, 18 ARM_CASE_PASS lines, ARM_FIR_ALL_PASS.\n"
        "Those strings describe expected output only; no target pass is claimed.\n"
        "Retain terminal output and outputs/ for independent verification.\n"
        "Programs process offline vectors; no RF, IIO, FPGA programming or persistence setup.\n",
        encoding="ascii", newline="\n")
    files = sorted(p for p in bundle.rglob("*") if p.is_file())
    (bundle / "SHA256SUMS").write_text("".join(f"{sha(p)}  {p.relative_to(bundle).as_posix()}\n" for p in files), encoding="ascii", newline="\n")
    archive = OUT / "arm-fir-check.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(bundle.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(OUT).as_posix())
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:
            raise RuntimeError("ZIP CRC failure")
    shutil.copy2(Path(__file__), OUT / Path(__file__).name)
    report = {"created_at_utc": datetime.now(timezone.utc).isoformat(), "scope": "Prepared only; board execution pending",
              "cases": cases, "total_outputs_including_reset_replay": sum(c["outputs_including_reset_replay"] for c in cases),
              "golden_manifest_sha256": sha(VECTORS / "manifest.json"), "cross_report_sha256": sha(CROSS / "report.json"),
              "bundle_zip_bytes": archive.stat().st_size, "bundle_zip_sha256": sha(archive), "zip_crc_passed": True,
              "board_run": "pending", "rf_access": False}
    (OUT / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"bundle": str(archive), "cases": len(cases), "board_run": "pending"}))


if __name__ == "__main__":
    main()
