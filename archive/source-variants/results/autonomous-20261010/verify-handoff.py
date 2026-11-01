"""Read current evidence and hashes, without rerunning hardware/tests or changing Git."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))

reports = [
    ROOT/"results/p07-fir-rtl-20261010T081533765282Z/report.json",
    ROOT/"results/p07-fir-rtl-20261010T081544645644Z/report.json",
    ROOT/"results/p07-c-reference-20261010T125054720966Z/report.json",
]
checks = []
for path in reports:
    report = load(path)
    if report["all_passed"] is not True:
        raise AssertionError(f"Failed report {path}")
    for source in report["sources"]:
        if digest(Path(source["path"])) != source["sha256"]:
            raise AssertionError(f"Source changed since formal run: {source['path']}")
    checks.append({"report": str(path.relative_to(ROOT)), "sha256": digest(path),
                   "all_passed": True, "case_count": report["case_count"],
                   "sources_still_match_formal_run": True})

full = load(reports[0])
assert full["case_count"] == 18 and full["sample_comparisons"] == 72356
assert all(int(case["metrics"]["rounding_checks"]) == 22 for case in full["cases"])
qualification = load(reports[1])
assert qualification["sample_comparisons"] == 1086
assert qualification["default_coefficient_initialization"] is True
assert qualification["random_stalls_enabled"] is False
c_report = load(reports[2])
assert c_report["complex_outputs_per_pass"] == 72356
assert c_report["complex_outputs_including_reset_replay"] == 144712
assert c_report["compiler_target"] == "x86_64-w64-mingw32"
assert c_report["board_accessed"] is False and c_report["arm_execution"] is False
assert c_report["all_126_vector_files_verified_before_C_execution"] is True

documents = [ROOT/"docs/implementation-guide.md", ROOT/"docs/experiments/EXP-P06.md",
             ROOT/"docs/experiments/EXP-P07a-FIXED-FIR.md", ROOT/"docs/experiments/EXP-AUTO-20261010.md"]
missing = []
for path in documents:
    for target in re.findall(r"\]\(([^)]+)\)", path.read_text(encoding="utf-8-sig")):
        if "://" in target or target.startswith("#"):
            continue
        resolved = (path.parent / target.split("#", 1)[0]).resolve()
        if not resolved.exists():
            missing.append({"document": str(path), "target": target})
if missing:
    raise AssertionError(f"Missing documentation link targets: {missing}")

index_sha = digest(ROOT/".git/index")
assert index_sha == "8ead9f45d19caee3dca3792831bc4856801334a17a87c00e6080834572cbc83d"
batch = load(ROOT/"results/p06-install-prep-20261010/batch-entry-check.json")
record = {
    "checked_at": datetime.now(timezone.utc).isoformat(),
    "scope": "saved_host_reference_simulation_and_handoff_integrity_not_board_acceptance",
    "evidence_reports": checks, "missing_documentation_targets": missing,
    "documents": [{"path": str(path.relative_to(ROOT)), "sha256": digest(path)} for path in documents],
    "git_index_unchanged_sha256": index_sha,
    "installer_batch_observation_saved": bool(batch),
    "all_handoff_checks_passed": True,
    "vivado_build_completed": False, "board_execution_completed": False,
}
(OUT/"handoff-verification.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
print("Handoff checks passed: formal source hashes, 18 RTL cases, qualification, 18 C cases, document links and unchanged Git index.")
