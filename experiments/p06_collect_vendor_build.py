"""Preserve a finished vendor build and audit coverage; never operate hardware."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
WORK = Path(r"E:\FPGA_Tools\Work\p06-pzp201-20261011c")
HDL = WORK / "hdl"
PROJECT = HDL / "projects/pzp201"
BUILD = WORK / "build-20261011-001248-d1f4cf"
OUT = ROOT / "results/p06-vendor-build-20261011"

def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()

def main():
    OUT.mkdir(exist_ok=True)
    if any(OUT.iterdir()):
        raise RuntimeError("Refusing to overwrite saved build evidence")
    manifest = json.loads((ROOT / "fpga/vendor-baseline/source-manifest.json").read_text(encoding="utf-8-sig"))
    source_checks = []
    for row in manifest["files"]:
        rel = Path(row["archive_member"]).relative_to("plutosdr-fw/hdl")
        path = HDL / rel
        actual = sha(path)
        immutable = ROOT / "fpga/vendor-baseline" / row["relative_path"]
        source_checks.append({"relative_path": rel.as_posix(), "sha256": actual,
                              "matches_original": actual == row["sha256"] and path.stat().st_size == row["bytes"],
                              "immutable_copy_matches": sha(immutable) == row["sha256"] and immutable.stat().st_size == row["bytes"]})
    changed = [x for x in source_checks if not x["matches_original"]]
    if (len(source_checks) != 138 or not all(x["immutable_copy_matches"] for x in source_checks)
            or [x["relative_path"] for x in changed] != ["library/axi_ad9361/bd/bd.tcl"]):
        raise RuntimeError("Vendor source provenance changed")
    record = json.loads((BUILD / "build-record.json").read_text(encoding="utf-8-sig"))
    if not record["successful"] or len(record["stages"]) != 8 or any(x["exit_code"] != 0 for x in record["stages"]):
        raise RuntimeError("Not a successfully exited full vendor build")
    copies = []
    def preserve(source, relative):
        target = OUT / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        digest = sha(source)
        if sha(target) != digest or target.stat().st_size == 0:
            raise RuntimeError(f"Evidence copy failed: {target}")
        copies.append({"source": str(source), "saved": relative, "bytes": target.stat().st_size, "sha256": digest})
    for source in BUILD.iterdir():
        if source.is_file():
            preserve(source, "build-logs/" + source.name)
    names = ["system_top_utilization_placed.rpt", "system_top_timing_summary_routed.rpt",
             "system_top_route_status.rpt", "system_top_drc_routed.rpt", "system_top_methodology_drc_routed.rpt", "runme.log"]
    for name in names:
        preserve(PROJECT / "pzp201.runs/impl_1" / name, "reports/" + name)
    for name in ["timing_synth.log", "timing_impl.log", "no_clock.log", "axi_ad9361_delay.log"]:
        preserve(PROJECT / name, "reports/" + name)
    preserve(PROJECT / "pzp201.sdk/system_top.xsa", "artifacts/system_top.xsa")
    preserve(PROJECT / "pzp201.runs/impl_1/system_top.bit", "artifacts/system_top.bit")
    preserve(PROJECT / "pzp201.runs/impl_1/system_top_routed.dcp", "artifacts/system_top_routed.dcp")
    for name in ["system_project.tcl", "system_constr.xdc", "system_bd.tcl"]:
        preserve(PROJECT / name, "sources/" + name)
    preserve(HDL / "library/axi_ad9361/bd/bd.tcl", "sources/regenerated-axi-ad9361-bd.tcl")
    ps_xdc = PROJECT / "pzp201.gen/sources_1/bd/system/ip/system_sys_ps7_0/system_sys_ps7_0.xdc"
    preserve(ps_xdc, "sources/generated-disabled-ps7.xdc")
    for name in ["build-vendor-baseline.ps1", "preflight-vivado.tcl"]:
        preserve(ROOT / "fpga/vendor-baseline" / name, "entrypoints/" + name)
    timing = (PROJECT / "timing_impl.log").read_text(encoding="utf-8")
    coverage = {k: int(re.search(r"checking " + k + r" \((\d+)\)", timing).group(1))
                for k in ["no_clock", "unconstrained_internal_endpoints", "no_input_delay", "no_output_delay"]}
    summary = re.search(r"\n\s*([+-]?[\d.]+)\s+([+-]?[\d.]+)\s+(\d+)\s+(\d+)\s+([+-]?[\d.]+)\s+([+-]?[\d.]+)\s+(\d+)\s+(\d+)\s+([+-]?[\d.]+)\s+([+-]?[\d.]+)\s+(\d+)\s+(\d+)\s*\n", timing)
    if summary is None:
        raise RuntimeError("Cannot identify official timing summary")
    summary_values = dict(zip(["wns_ns", "tns_ns", "setup_failing_endpoints", "setup_total_endpoints",
                              "whs_ns", "ths_ns", "hold_failing_endpoints", "hold_total_endpoints",
                              "wpws_ns", "tpws_ns", "pulse_failing_endpoints", "pulse_total_endpoints"],
                             [float(x) for x in summary.groups()]))
    util = (PROJECT / "pzp201.runs/impl_1/system_top_utilization_placed.rpt").read_text(encoding="utf-8")
    resources = {}
    for name in ["Slice LUTs", "Slice Registers", "Block RAM Tile", "DSPs"]:
        match = re.search(r"^\|\s*" + re.escape(name) + r"\s*\|\s*(\d+)\s*\|\s*\d+\s*\|\s*\d+\s*\|\s*(\d+)\s*\|\s*([\d.]+)", util, re.M)
        if match is None:
            raise RuntimeError(f"Resource row absent: {name}")
        resources[name] = {"used": int(match[1]), "available": int(match[2]), "percent": float(match[3])}
    log = (BUILD / "07-pzp201-original-project.log").read_text(encoding="utf-8")
    diagnostics = [line for line in log.splitlines() if re.match(r"^(ERROR:|CRITICAL WARNING:)", line)]
    (OUT / "critical-diagnostics.txt").write_text("\n".join(diagnostics) + "\n", encoding="utf-8")
    with zipfile.ZipFile(PROJECT / "pzp201.sdk/system_top.xsa") as archive:
        bad = archive.testzip()
        if bad is not None:
            raise RuntimeError(f"XSA zip CRC failed: {bad}")
        xsa_members = [{"name": x.filename, "bytes": x.file_size} for x in archive.infolist()]
        embedded_bits = [x for x in archive.namelist() if x.endswith(".bit")]
        xsa_bits_match = bool(embedded_bits) and all(hashlib.sha256(archive.read(x)).hexdigest() == sha(PROJECT / "pzp201.runs/impl_1/system_top.bit") for x in embedded_bits)
    report = {"audited_at_utc": datetime.now(timezone.utc).isoformat(), "build": record,
              "source_checks": source_checks, "build_regenerated_files": changed,
              "source_provenance_note": "138 immutable original files remain unchanged and were checked before build. Original packaging auto-regenerated library/axi_ad9361/bd/bd.tcl in the disposable work tree; regenerated bytes are preserved separately.",
              "preserved_files": copies, "resources": resources,
              "timing_summary_existing_constraints": summary_values, "constraint_coverage": coverage,
              "clock_coverage_explanation": "Original system_project.tcl explicitly disables system_sys_ps7_0.xdc; only rx_clk is present. PS FCLK0/1 source configuration is 100/200 MHz but those constraints were disabled.",
              "build_and_artifacts_passed": True, "all_timing_accepted": False,
              "board_programmed": False, "new_bitstream_rx_verified": False,
              "xsa_zip_crc_passed": True, "xsa_embedded_bit_matches": xsa_bits_match, "xsa_members": xsa_members,
              "critical_diagnostic_count": len(diagnostics)}
    (OUT / "audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"build_artifacts_passed": True, "resources": resources, "constraint_coverage": coverage,
                      "all_timing_accepted": False, "xsa_embedded_bit_matches": xsa_bits_match, "saved": str(OUT)}, ensure_ascii=False))

if __name__ == "__main__":
    main()
