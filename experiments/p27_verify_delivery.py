"""Check P27 saved evidence and hashes without touching either board."""
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import unquote
import xml.etree.ElementTree as ET

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    state_path = ROOT / "TX-SOURCE-STATUS.json"
    state = read(state_path)
    current = state["p27_native_diagnostic"]
    acq_path = ROOT / current["acquisition"]
    analysis_path = ROOT / current["analysis"]
    acq, analysis = read(acq_path), read(analysis_path)
    metadata = acq["native_metadata"]
    assessment = analysis["assessment"]
    testlog = ROOT / state["python_tests_evidence"]
    xml_path = testlog.with_name("pytest.xml")
    suites = ET.parse(xml_path).getroot().findall(".//testsuite")
    counts = {k: sum(int(s.attrib.get(k, 0)) for s in suites)
              for k in ("tests", "failures", "errors", "skipped")}
    require(counts == dict(tests=864, failures=0, errors=0, skipped=0),
            "JUnit acceptance does not match the complete 864-test run")
    require(state["python_tests"] == 864 and
            re.search(r"\b864 passed\b", testlog.read_text("utf-8")),
            "state/test log disagree")
    files = {state_path, testlog, xml_path, acq_path, analysis_path}

    build_path = Path(acq["build"])
    build = read(build_path)
    source = ROOT / "embedded/arm_rx_diagnostic/arm_rx_diagnostic.c"
    archived_source = build_path.with_name("source.c")
    binary = Path(build["binary"])
    require(build["status"] == "cross_compile_verified", "build incomplete")
    require(sha(source) == sha(archived_source) == build["source_sha256"],
            "compiled source differs from delivered source")
    require(sha(binary) == build["binary_sha256"], "binary hash changed")
    files.update((build_path, source, archived_source, binary, Path(acq["smoke"])))

    require(acq["status"] == "capture_and_tx_cleanup_verified", "capture not accepted")
    require(acq["tx_duration_limit_s"] == 30 and
            "TX_CLEANUP buffer_released=true rf_settings_written=false status=0" in acq["tx_end"] and
            "DDS_ZERO_SOURCE_READBACK=PASS" in acq["tx_end"] and
            "__P27_TX_RC__:0" in acq["tx_end"], "bounded TX cleanup evidence missing")
    require(metadata["buffer_released"] is True and metadata["blocks"] == 512,
            "native capture/release incomplete")
    for report in (acq, analysis, current):
        require(report["complete_stream_saved"] is False, "false complete-stream claim")
    for report in (metadata, analysis, assessment, current):
        require(report["lossless_proven"] is False, "false lossless claim")
    require(acq["RF_attributes_written"] is False and
            metadata["RF_attributes_written"] is False, "unexpected RF configuration change")
    require(analysis["native_metadata"] == metadata, "analysis/capture metadata differ")
    require(metadata["channels"] == 2 and metadata["dma_frames"] == 65536 and
            metadata["kept_frames_per_block"] == 1024 and metadata["stride"] == 8,
            "native layout differs from documented scope")
    require(analysis["saved_sample_fraction"] == current["saved_sample_fraction"] == 0.015625,
            "saved fraction incorrect")
    require(assessment["status"] == "modulo_consistent" and
            assessment["usable_windows"] == assessment["total_windows"] == 512 and
            assessment["detected_jump_count"] == assessment["unverified_boundary_count"] == 0 and
            len(assessment["boundaries"]) == 511, "analysis acceptance changed")
    require(len(analysis["windows"]) == 512 and all(
        w["correlation"] >= assessment["minimum_correlation"] for w in analysis["windows"]),
        "weak or absent source observations")

    raw_path = ROOT / analysis["source"]
    transfer_path = raw_path.with_name("report.json")
    transfer = read(transfer_path)
    require(transfer["status"] == "all_payloads_verified" and
            Path(transfer["acquisition"]).resolve() == acq_path.parent.resolve(),
            "wrong or unfinished transfer")
    require(transfer["diagnostic_only"] is True and
            transfer["complete_stream_saved"] is False, "incorrect transfer scope")
    require(len(transfer["files"]) == len(acq["board_files"]) == 1, "unexpected payload set")
    entry, board_entry = transfer["files"][0], acq["board_files"][0]
    require(raw_path.name == entry["local_file"] and entry["sha256"] ==
            board_entry["sha256"] == analysis["source_sha256"], "payload association changed")
    packed = []
    for part in sorted(entry["chunks"], key=lambda x: x["index"]):
        path = transfer_path.parent / part["file"]
        require(path.stat().st_size == part["bytes"] and sha(path) == part["sha256"],
                "compressed chunk changed")
        packed.append(path.read_bytes())
        files.add(path)
    payload = b"".join(packed)
    require(len(payload) == entry["gzip_bytes"] and
            hashlib.sha256(payload).hexdigest() == entry["gzip_sha256"],
            "board compressed hash mismatch")
    require(gzip.decompress(payload) == raw_path.read_bytes() and
            sha(raw_path) == entry["sha256"] and
            raw_path.stat().st_size == entry["expected_bytes"] == 2097152,
            "raw payload mismatch")
    values = np.fromfile(raw_path, dtype="<i2")
    require(values.size == 512 * 1024 * 2 and values.min() >= -2048 and values.max() <= 2047,
            "noncanonical signed 12-bit stored payload")
    files.update((raw_path, transfer_path))

    readiness_path = ROOT / state["new_board_build_readiness"]["evidence"]
    readiness = read(readiness_path)
    require(readiness["status"] == "synthesis_capability_blocked" and readiness["exit_code"] == 3,
            "build condition changed; review recorded conclusion")
    require(state["new_board_build_readiness"]["checkout_attempted"] is False,
            "unexpected license checkout assertion")
    files.add(readiness_path)
    docs = [ROOT / name for name in ("START-HERE.md", "README.md", "docs/implementation-guide.md",
            "docs/handoff/RESUME-20261018.md", "docs/design/new-board-tlz7xh-evm-review-20261017.md",
            state["record"])]
    links = []
    for path in docs:
        files.add(path)
        body = re.sub(r"```.*?```", "", path.read_text("utf-8"), flags=re.S)
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", body):
            if target.startswith(("https:", "http:", "#", "mailto:")):
                continue
            clean = unquote(target.strip("<>").split("#", 1)[0])
            destination = (path.parent / clean).resolve()
            require(destination.exists(), f"broken local link: {path}: {target}")
            links.append({"document": path.relative_to(ROOT).as_posix(), "target": target})
    files.update((ROOT / "experiments").glob("p27_*.py"))
    files.update(ROOT / name for name in ("src/rfsig/sparse_continuity.py",
                 "tests/native/mock_rx_diagnostic.c", "tests/test_native_rx_diagnostic.py",
                 "tests/test_sparse_continuity.py", "experiments/p26_retrieve_chunks.py"))
    files.update(ROOT.glob("results/p27-observer-validation-*/report.json"))
    files.update(ROOT.glob("results/p27-summary-*/diagnostic.png"))
    out = ROOT / "results" / datetime.now(timezone.utc).strftime("p27-delivery-verification-%Y%m%dT%H%M%SZ")
    out.mkdir(exist_ok=False)
    manifest = {"created_utc": datetime.now(timezone.utc).isoformat(), "status": "verified",
        "test_counts": counts, "sparse_payload_bytes": raw_path.stat().st_size,
        "saved_sample_fraction": 0.015625, "usable_windows": 512, "boundaries": 511,
        "detected_nonperiodic_jumps": 0, "complete_stream_saved": False, "lossless_proven": False,
        "document_links": links, "hardware_operations": False,
        "files": [{"path": path.relative_to(ROOT).as_posix(), "bytes": path.stat().st_size,
                   "sha256": sha(path)} for path in sorted(files)],
        "limit": "Offline evidence/hash verification adds no new physical RF, lossless-stream, AI or display evidence."}
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                       encoding="utf-8", newline="\n")
    print(f"Verified {counts['tests']} tests, {len(entry['chunks'])} chunks, {len(links)} links, {len(files)} manifest files.")
    print(out)


if __name__ == "__main__":
    main()
