"""Independently verify retrieved ARM outputs against the validated golden bundle."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
import tarfile

import numpy as np


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    bundle = root / "results/p07-arm-board-bundle-20261011/arm-fir-check"
    evidence = args.evidence.resolve()
    report_file = evidence / "output-verification.json"
    if report_file.exists() or (evidence / "outputs").exists():
        raise RuntimeError("Verification output already exists; refusing overwrite")
    transfer = json.loads((evidence / "report.json").read_text(encoding="utf-8-sig"))
    archive = evidence / "board-results.tar.gz"
    archive_bytes = archive.read_bytes()
    assert len(archive_bytes) == transfer["archive_bytes"]
    assert hashlib.sha256(archive_bytes).hexdigest() == transfer["archive_sha256"]
    assert transfer["status"] == "results_retrieved_checksum_passed_content_verification_pending"

    source_checks = 0
    for line in (bundle / "SHA256SUMS").read_text().splitlines():
        digest, filename = line.split(maxsplit=1)
        filename = filename.lstrip("*")
        path = (bundle / filename).resolve()
        assert path.is_relative_to(bundle.resolve())
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
        source_checks += 1
    assert source_checks == 82
    expected_paths = sorted((bundle / "expected").glob("*.csv"))
    expected_names = {f"outputs/{p.name}" for p in expected_paths}
    expected_names.update({"outputs/hello.txt", "outputs/fir-smoke.txt", "outputs/uname.txt"})
    assert len(expected_paths) == 18
    payloads = {}
    total = 0
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar:
            name = str(PurePosixPath(member.name))
            assert not PurePosixPath(member.name).is_absolute()
            assert ".." not in PurePosixPath(member.name).parts
            if member.isdir():
                assert name == "outputs"
                continue
            assert member.isfile() and name in expected_names and name not in payloads
            total += member.size
            assert total <= 16 * 1024 * 1024
            data = tar.extractfile(member).read()
            assert len(data) == member.size
            payloads[name] = data
    assert set(payloads) == expected_names
    assert "Linux pzp201" in payloads["outputs/uname.txt"].decode()
    assert "armv7l" in payloads["outputs/uname.txt"].decode()
    assert "ARM_HELLO_PASS" in payloads["outputs/hello.txt"].decode()
    assert "ARM_FIR_SMOKE_PASS outputs=2 I=1,1 Q=-1,-1" in payloads["outputs/fir-smoke.txt"].decode()
    cases = []
    total_outputs = 0
    for expected in expected_paths:
        actual = payloads[f"outputs/{expected.name}"]
        assert actual == expected.read_bytes(), f"Golden mismatch: {expected.stem}"
        values = np.loadtxt(actual.decode().splitlines(), delimiter=",", dtype=np.int64)
        assert values.ndim == 2 and values.shape[1] == 6
        assert len(values) % 2 == 0
        assert np.array_equal(values[:len(values)//2], values[len(values)//2:])
        assert np.all((values[:, 2:4] == 0) | (values[:, 2:4] == 1))
        total_outputs += len(values)
        cases.append({"case": expected.stem, "outputs_including_reset_replay": len(values),
                      "sha256": hashlib.sha256(actual).hexdigest(), "byte_exact": True,
                      "reset_replay_identical": True, "columns": 6})
    assert total_outputs == 144712
    (evidence / "outputs").mkdir()
    for name, data in payloads.items():
        (evidence / name).write_bytes(data)
    report = {"at_utc": datetime.now(timezone.utc).isoformat(), "status": "passed",
              "source_bundle_files_rechecked": source_checks,
              "archive_sha256": transfer["archive_sha256"], "retrieved_files": len(payloads),
              "cases": cases, "complex_outputs": total_outputs,
              "board_execution": "actual ARMv7 Linux via COM5",
              "verified_fields": ["I", "Q", "saturation_I", "saturation_Q", "accumulator_I", "accumulator_Q"],
              "rf_or_fpga_operations": False,
              "unverified": ["live RX integration", "performance", "FPGA deployment", "AI inference"]}
    report_file.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "passed", "cases": len(cases), "outputs": total_outputs,
                      "files": len(payloads), "report": str(report_file)}))


if __name__ == "__main__":
    main()
