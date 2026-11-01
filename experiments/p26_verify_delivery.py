"""Verify review evidence, current status, source hashes and document links."""
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import unquote
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    out=ROOT/"results"/datetime.now(timezone.utc).strftime("p26-delivery-verification-%Y%m%dT%H%M%SZ")
    out.mkdir(exist_ok=False)
    state=json.loads((ROOT/"TX-SOURCE-STATUS.json").read_text("utf-8"))
    testlog=ROOT/state["python_tests_evidence"]
    xml=ET.parse(testlog.with_name("pytest.xml")).getroot()
    suites=xml.findall(".//testsuite")
    actual_tests=sum(int(s.attrib["tests"]) for s in suites)
    failures=sum(int(s.attrib["failures"])+int(s.attrib["errors"]) for s in suites)
    if actual_tests!=state["python_tests"] or failures:
        raise RuntimeError("test log/state/JUnit disagree")
    manifest_files={ROOT/"TX-SOURCE-STATUS.json",testlog,testlog.with_name("pytest.xml")}
    checked=[]
    for folder in ("p26-chunk-transfer-20261018T120112Z","p26-chunk-transfer-20261018T122135Z"):
        root=ROOT/"results"/folder
        trace=root/"report.json"
        report=json.loads(trace.read_text("utf-8"))
        if report["status"]!="all_payloads_verified":
            raise RuntimeError("unfinished capture transfer")
        manifest_files.add(trace)
        acquisition=Path(report["acquisition"])/"report.json"
        manifest_files.add(acquisition)
        for entry in report["files"]:
            path=root/entry["local_file"]
            chunks=[]
            for part in sorted(entry["chunks"],key=lambda c:c["index"]):
                part_path=root/part["file"]
                payload=part_path.read_bytes()
                if len(payload)!=part["bytes"] or digest(part_path)!=part["sha256"]:
                    raise RuntimeError("saved compressed chunk mismatch")
                chunks.append(payload)
            packed=b"".join(chunks)
            if hashlib.sha256(packed).hexdigest()!=entry["gzip_sha256"]:
                raise RuntimeError("board gzip hash mismatch")
            if gzip.decompress(packed)!=path.read_bytes() or digest(path)!=entry["sha256"]:
                raise RuntimeError("raw file differs from transported board payload")
            if path.stat().st_size!=entry["expected_bytes"]:
                raise RuntimeError("raw size/layout mismatch")
            checked.append({"path":path.relative_to(ROOT).as_posix(),"bytes":path.stat().st_size,"sha256":digest(path)})
            manifest_files.add(path)
    boot_path=ROOT/state["review_p26"]["boot"]
    boot=json.loads(boot_path.read_text("utf-8"))
    script=ROOT/"board/boot/S99board"
    if boot["boot_id_before"]==boot["boot_id_after"] or boot["status"]!="warm_boot_and_three_device_readiness_verified":
        raise RuntimeError("reboot acceptance invalid")
    if not any(digest(script) in s["output"] for s in boot["stages"] if s["command"]=="sha256sum /etc/rcS.d/S99board"):
        raise RuntimeError("deployed script differs from local source")
    manifest_files|={boot_path,script,ROOT/state["review_p26"]["rx_profile_restore"],ROOT/state["review_p26"]["evidence"],
                     ROOT/state["review_p26"]["rx1_symbol_quality"]["evidence"]}
    docs=[ROOT/"START-HERE.md",ROOT/"board/README.md",ROOT/"docs/handoff/RESUME-20261018.md",
          ROOT/"README.md",ROOT/"docs/implementation-guide.md"]
    docs+=sorted((ROOT/"docs/experiments").glob("EXP-HW-01[5-8]-*.md"))
    links=[]
    for path in docs:
        manifest_files.add(path)
        text=re.sub(r"```.*?```","",path.read_text("utf-8"),flags=re.S)
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)",text):
            if target.startswith(("http:","https:","#","mailto:")):
                continue
            clean=unquote(target.strip("<>").split("#",1)[0])
            dest=(path.parent/clean).resolve()
            links.append({"document":path.relative_to(ROOT).as_posix(),"target":target,"exists":dest.exists()})
            if not dest.exists():
                raise FileNotFoundError(str(path)+": "+target)
    for path in (ROOT/"experiments").glob("p26_*.py"):
        manifest_files.add(path)
    for path in [ROOT/"src/rfsig"/name for name in ("carrier_tracking.py","capture_continuity.py","reference_receiver.py")]:
        manifest_files.add(path)
    for name in ("test_progress_assessment.py","test_rotation_alignment.py","test_reference_receiver.py",
                 "test_snapshot_carrier.py","test_board_rf_readiness.py","test_continuity_check_failures.py","test_serial_attribute_frame.py"):
        manifest_files.add(ROOT/"tests"/name)
    manifest_files|={ROOT/"experiments/p23_features_continuous.py",ROOT/"experiments/p23_qam16_evm_diagnosis.py",
                     ROOT/"experiments/p25_continuity_check.py",ROOT/"configs/rf-link-snapshot-p26.json"}
    manifest={"created_utc":datetime.now(timezone.utc).isoformat(),"status":"verified",
              "tests":actual_tests,"test_failures_and_errors":failures,"raw_capture_checks":checked,
              "document_links":links,"files":[{"path":path.relative_to(ROOT).as_posix(),"bytes":path.stat().st_size,"sha256":digest(path)}
                                                 for path in sorted(manifest_files)],
              "hardware_writes":False,"limit":"File/hash validation does not add new physical RF, long-stream or AI evidence."}
    (out/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8",newline="\n")
    print("Verified",actual_tests,"tests,",len(checked),"full raw captures,",len(links),"document links,",len(manifest_files),"manifest files.")
    print(out)


if __name__=="__main__":
    main()
