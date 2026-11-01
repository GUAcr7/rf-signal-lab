"""Seal the source candidate and verify existing evidence without hardware."""
import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path
import re
import shutil
import sys
import tarfile
import zipfile

from rfsig.tx_package import file_hash, verify_tx_package

ROOT = Path(__file__).resolve().parents[1]
INDEX_SHA = "8ead9f45d19caee3dca3792831bc4856801334a17a87c00e6080834572cbc83d"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--delivery", type=Path, required=True)
    parser.add_argument("--regression", type=Path, required=True)
    args = parser.parse_args()
    delivery = json.loads((args.delivery / "report.json").read_text(encoding="utf-8"))
    archive = Path(delivery["archive"])
    if file_hash(archive) != delivery["archive_sha256"]:
        raise ValueError("Combined delivery changed")
    if file_hash(ROOT / ".git/index") != INDEX_SHA:
        raise ValueError("Existing Git staged index changed")
    regression = json.loads((args.regression / "report.json").read_text(encoding="utf-8-sig"))
    match = re.search(r"(\d+) passed", (args.regression / "pytest.txt").read_text(encoding="utf-8-sig"))
    if regression["exit_code"] != 0 or match is None:
        raise ValueError("Final Python regression did not pass")
    if file_hash(ROOT / "embedded/arm_tx_source/arm_tx_source.c") != delivery["source_sha256"]:
        raise ValueError("Current native source differs from delivered executable's source")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    out = ROOT / "results" / ("p12-final-freeze-" + stamp)
    snapshot = out / "source-snapshot"
    snapshot.mkdir(parents=True)
    files = [ROOT / name for name in ("README.md", "START-HERE.md", "pyproject.toml", "pytest.ini", "requirements-lock.txt",
        "run-tx-source-inspect.cmd", "host/tx_source.py", "embedded/arm_tx_source/arm_tx_source.c",
        "embedded/vendor/libiio-v0.24/iio.h", "embedded/vendor/libiio-v0.24/source.json",
        "docs/implementation-guide.md", "docs/design/two-board-rf-link.md",
        "docs/design/new-board-ad9361-review-20261016.md", "docs/experiments/EXP-TX-SOURCE-20261016.md",
        "docs/experiments/EXP-AUTO-20261016.md", "tests/native/tx_mock_iio.c")]
    files += list((ROOT / "experiments").glob("p12*"))
    for name in ("tx_waveforms", "tx_package", "rf_link_budget", "iio_runtime", "bpsk", "modulation", "pulse_shaping"):
        files.append(ROOT / "src/rfsig" / (name + ".py"))
    for name in ("tx_waveforms", "tx_package", "rf_link_budget"):
        files.append(ROOT / "tests" / ("test_" + name + ".py"))
    # Freeze native format and DDS-order references, not the whole vendor tree.
    files.append(ROOT / "fpga/vendor-baseline/source/plutosdr-fw/hdl/library/axi_ad9361/axi_ad9361_tx_channel.v")
    files.append(ROOT / "fpga/vendor-baseline/source/plutosdr-fw/hdl/projects/pzp201/system_bd.tcl")
    files.append(ROOT / "fpga/vendor-baseline/source/plutosdr-fw/hdl/projects/common/xilinx/adi_fir_filter_bd.tcl")
    for name in ("dsp.py", "rx_tx.py", "compat.py"):
        files.append(ROOT / ".venv/Lib/site-packages/adi" / name)
    sources = []
    links = []
    for source in sorted(set(files)):
        if not source.is_file():
            raise ValueError(f"Source missing: {source}")
        relative = source.relative_to(ROOT)
        target = snapshot / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        digest = file_hash(source)
        if file_hash(target) != digest:
            raise ValueError("Snapshot mismatch")
        sources.append(dict(path=relative.as_posix(), bytes=source.stat().st_size, sha256=digest))
        if source.suffix == ".md":
            for link in re.findall(r"\]\(([^)]+)\)", source.read_text(encoding="utf-8")):
                if "://" in link or link.startswith(("#", "mailto:")):
                    continue
                filename = link.split("#", 1)[0].strip("<>")
                if filename and not (source.parent / filename).exists():
                    links.append(dict(source=relative.as_posix(), missing=filename))
    if links:
        raise ValueError(f"Missing local documentation targets: {links}")
    bundle = args.delivery / delivery["prefix"]
    inner = []
    for line in (bundle / "SHA256SUMS").read_text(encoding="ascii").splitlines():
        digest, filename = line.split("  ", 1)
        path = bundle / filename
        if file_hash(path) != digest:
            raise ValueError("Delivered member mismatch")
        inner.append(dict(path=filename, sha256=digest))
    # Read back the tar; do not extract or execute its ARM contents.
    with tarfile.open(archive, "r:") as tar:
        for row in inner:
            member = tar.getmember(delivery["prefix"] + "/" + row["path"])
            stream = tar.extractfile(member)
            import hashlib
            if stream is None or hashlib.file_digest(stream, "sha256").hexdigest() != row["sha256"]:
                raise ValueError("Archive member mismatch")
    packages = [verify_tx_package(item["source"]) for item in delivery["packages"]]
    inventory = json.loads((ROOT / "results/p12-new-board-review-20261016/source-inventory.json").read_text(encoding="utf-8"))
    checked_hashes = 0
    for item in inventory["items"]:
        path = Path(item["path"])
        if path.stat().st_size != item["bytes"]:
            raise ValueError("Original supplied material size changed")
        if item.get("sha256"):
            if file_hash(path) != item["sha256"]:
                raise ValueError("Original supplied material digest changed")
            checked_hashes += 1
    package_versions = {}
    for name in ("numpy", "pytest", "matplotlib", "pyadi-iio", "pylibiio"):
        try: package_versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError: package_versions[name] = "distribution metadata unavailable"
    report = dict(status="candidate_source_delivery_evidence_sealed_RF_and_board_pending",
                  created_utc=datetime.now(timezone.utc).isoformat(), python=sys.version,
                  package_versions=package_versions, source_files=len(sources),
                  delivery=str(args.delivery.resolve()), archive=str(archive), archive_sha256=delivery["archive_sha256"],
                  archive_inner_files_checked=len(inner), offline_waveform_files_checked=sum(len(p["waveforms"]) for p in packages),
                  supplied_material_sizes_checked=len(inventory["items"]), supplied_material_hashes_checked=checked_hashes,
                  git_index_sha256=INDEX_SHA, regression=str(args.regression.resolve()), python_tests=int(match.group(1)),
                  board_files_written=False, RF_transmitted=False, markdown_missing_local_targets=links,
                  native_source_sha256=delivery["source_sha256"], native_binary_sha256=delivery["binary_sha256"])
    (out / "manifest.json").write_text(json.dumps(sources, indent=2) + "\n", encoding="utf-8")
    (out / "verification.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    with zipfile.ZipFile(out / "sources.zip", "w", zipfile.ZIP_DEFLATED) as saved:
        for row in sources:
            saved.write(snapshot / row["path"], row["path"])
    print(json.dumps(dict(output=str(out), **report)))


if __name__ == "__main__":
    main()
