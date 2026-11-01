"""Create a new short-path workspace from the verified pristine source copy."""
from pathlib import Path
import datetime as dt
import hashlib
import json
import shutil

record_dir = Path(__file__).resolve().parent
baseline = record_dir.parent.parent / "fpga" / "vendor-baseline"
manifest = json.loads((baseline / "source-manifest.json").read_text(encoding="utf-8"))
work_root = Path(r"E:\FPGA_Tools\Work\p06-pzp201")
if work_root.exists():
    work_root = work_root.with_name("p06-pzp201-" + dt.datetime.now().strftime("%Y%m%d-%H%M%S"))
if work_root.exists():
    raise FileExistsError(work_root)
hdl_root = work_root / "hdl"
copies = []
prefix = "source/plutosdr-fw/hdl/"
for row in manifest["files"]:
    if not row["relative_path"].startswith(prefix):
        raise ValueError("Manifest source escaped HDL root")
    source = baseline.joinpath(*row["relative_path"].split("/"))
    source.resolve().relative_to((baseline / "source").resolve())
    data = source.read_bytes()
    if len(data) != row["bytes"] or hashlib.sha256(data).hexdigest() != row["sha256"]:
        raise ValueError(f"Pristine source changed: {source}")
work_root.mkdir(parents=True, exist_ok=False)
for row in manifest["files"]:
    source = baseline.joinpath(*row["relative_path"].split("/"))
    target = hdl_root.joinpath(*row["relative_path"][len(prefix):].split("/"))
    target.resolve().relative_to(hdl_root.resolve())
    target.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as input_file, target.open("xb") as output:
        shutil.copyfileobj(input_file, output)
    if target.stat().st_size != row["bytes"] or hashlib.sha256(target.read_bytes()).hexdigest() != row["sha256"]:
        raise ValueError(f"Workspace hash mismatch: {target}")
    copies.append({"hdl_relative_path": row["relative_path"][len(prefix):], "bytes": row["bytes"], "sha256": row["sha256"]})
record = {"prepared_at": dt.datetime.now(dt.timezone.utc).isoformat(), "work_root": str(work_root), "hdl_root": str(hdl_root), "pristine_manifest": str(baseline / "source-manifest.json"), "file_count": len(copies), "source_bytes": sum(row["bytes"] for row in copies), "all_hashes_match_pristine": True, "existing_workspace_overwritten": False, "vivado_started": False, "files": copies}
for output in (record_dir / "short-workspace-manifest.json", baseline / "short-workspace-manifest.json"):
    output.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({key: value for key, value in record.items() if key != "files"}, ensure_ascii=False, indent=2))
