"""Select the PZP201 Xilinx source closure and copy bytes from the indexed tar."""
from pathlib import Path, PurePosixPath
import datetime as dt
import hashlib
import json
import posixpath
import re

record_dir = Path(__file__).resolve().parent
baseline = record_dir.parent.parent / "fpga" / "vendor-baseline"
destination = baseline / "source"
index = json.loads((record_dir / "archive-source-index.json").read_text(encoding="utf-8"))
archive_path = Path(index["archive"])
before = archive_path.stat()
if (before.st_size, before.st_mtime_ns) != (index["archive_bytes"], index["archive_mtime_ns"]):
    raise ValueError("Archive changed after inventory")
rows = {}
for row in index["entries"]:
    if row["name"] in rows:
        raise ValueError(f"Duplicate indexed entry: {row['name']}")
    rows[row["name"]] = row
hdl_prefix = "plutosdr-fw/hdl/"
selected = set()
reasons = {}
missing = []
library_order = []
library_graph = {}
make_dependencies = []
literal_dependencies = []
texts = {}

def select(name, reason):
    name = posixpath.normpath(name)
    if not name.startswith(hdl_prefix):
        raise ValueError(f"Dependency escaped HDL root: {name}")
    row = rows.get(name)
    if not row or row["kind"] != "file":
        missing.append({"name": name, "reason": reason})
        return False
    selected.add(name)
    reasons.setdefault(name, []).append(reason)
    return True

def read(name):
    if name not in texts:
        row = rows[name]
        archive.seek(row["offset_data"])
        data = archive.read(row["size"])
        if len(data) != row["size"]:
            raise ValueError(f"Truncated source: {name}")
        texts[name] = data.decode("utf-8", errors="strict")
    return texts[name]

def inspect_makefile(name):
    select(name, "original build entry")
    base = posixpath.dirname(name)
    libraries = []
    for line in read(name).splitlines():
        match = re.match(r"\s*(GENERIC_DEPS|XILINX_DEPS|M_DEPS)\s*\+=\s*([^#]+)", line)
        if match and "$" not in match[2]:
            for path in match[2].split():
                dep = posixpath.normpath(posixpath.join(base, path))
                make_dependencies.append({"source": name, "name": dep, "variable": match[1]})
                select(dep, f"{name}: {match[1]}")
        match = re.match(r"\s*(?:LIB_DEPS|XILINX_LIB_DEPS|XILINX_INTERFACE_DEPS)\s*\+=\s*([^#]+)", line)
        if match:
            if "$" in match[1]:
                raise ValueError(f"Unresolved library dependency: {name}: {line}")
            libraries.extend(match[1].split())
        match = re.match(r"\s*include\s+([^#\s]+)", line)
        if match and "$" not in match[1]:
            select(posixpath.join(base, match[1]), f"{name}: include")
    return libraries

def library(lib, visiting=()):
    if lib in library_order:
        return
    if lib in visiting:
        raise ValueError(f"Library dependency cycle: {visiting}, {lib}")
    makefile = hdl_prefix + "library/" + lib + "/Makefile"
    children = inspect_makefile(makefile)
    library_graph[lib] = children
    for child in children:
        library(child, visiting + (lib,))
    library_order.append(lib)

with archive_path.open("rb") as archive:
    project_libraries = inspect_makefile(hdl_prefix + "projects/pzp201/Makefile")
    for lib in project_libraries:
        library(lib)
    for name in ("Makefile", "README.md", "quiet.mk", ".gitattributes", ".gitignore", "LICENSE", "LICENSE_ADIBSD", "LICENSE_GPL2", "LICENSE_LGPL", "LICENSE_BSD-1-Clause"):
        select(hdl_prefix + name, "HDL build configuration, documentation, or license")
    for name in ("system_project.tcl", "system_bd.tcl", "system_top.v", "system_constr.xdc"):
        select(hdl_prefix + "projects/pzp201/" + name, "original PZP201 source entry")
    for name in ("adi_env.tcl", "adi_project_xilinx.tcl", "adi_board.tcl", "adi_xilinx_msg.tcl", "project-xilinx.mk"):
        select(hdl_prefix + "projects/scripts/" + name, "shared Xilinx project build support")
    for name in ("adi_env.tcl", "adi_ip_xilinx.tcl", "adi_xilinx_device_info_enc.tcl", "library.mk"):
        select(hdl_prefix + "library/scripts/" + name, "shared Xilinx IP packaging support")
    examined = set()
    extensions = r"(?:tcl|ttcl|v|vh|sv|svh|vhd|xdc|coe|mem|xml|mk)"
    while selected - examined:
        name = sorted(selected - examined)[0]
        examined.add(name)
        if not name.endswith((".tcl", ".ttcl", ".v", ".vh", ".sv", ".svh", ".xdc", ".mk")):
            continue
        text = read(name)
        for match in re.finditer(r"\$ad_hdl_dir/([A-Za-z0-9_./-]+\." + extensions + r")", text):
            dep = hdl_prefix + match[1]
            if dep in rows:
                literal_dependencies.append({"source": name, "name": dep, "reference": "ADI_HDL_DIR literal"})
                select(dep, f"{name}: explicit ADI_HDL_DIR input")
        for match in re.finditer(r'"([A-Za-z0-9_./-]+\.' + extensions + r')"', text):
            dep = posixpath.normpath(posixpath.join(posixpath.dirname(name), match[1]))
            if dep in rows:
                literal_dependencies.append({"source": name, "name": dep, "reference": "quoted relative input"})
                select(dep, f"{name}: quoted relative input")
        for match in re.finditer(r'^\s*source\s+([A-Za-z0-9_./-]+\.tcl)', text, re.MULTILINE):
            runtime_directory = posixpath.dirname(name)
            if name.startswith(hdl_prefix + "projects/scripts/"):
                runtime_directory = hdl_prefix + "projects/pzp201"
            dep = posixpath.normpath(posixpath.join(runtime_directory, match[1]))
            select(dep, f"{name}: source")
    (record_dir / "missing-source-files.json").write_text(json.dumps(missing, indent=2), encoding="utf-8")
    if missing:
        raise ValueError(f"Missing required dependencies: {len(missing)}")
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("Source destination must be new or empty")
    destination.mkdir(parents=True, exist_ok=True)
    seen = set()
    manifest = []
    for name in sorted(selected):
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name:
            raise ValueError(f"Unsafe source path: {name}")
        for component in path.parts:
            stem = component.split(".", 1)[0].upper()
            if component.endswith((".", " ")) or any(c in '<>"|?*' or ord(c) < 32 for c in component):
                raise ValueError(f"Invalid Windows source path: {name}")
            if stem in {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"} or re.fullmatch(r"(?:COM|LPT)[1-9¹²³]", stem):
                raise ValueError(f"Reserved Windows source path: {name}")
        if name.casefold() in seen:
            raise ValueError(f"Windows case collision: {name}")
        seen.add(name.casefold())
        row = rows[name]
        target = destination.joinpath(*path.parts)
        target.resolve().relative_to(destination.resolve())
        target.parent.mkdir(parents=True, exist_ok=True)
        archive.seek(row["offset_data"])
        data = archive.read(row["size"])
        if len(data) != row["size"]:
            raise ValueError(f"Truncated source payload: {name}")
        digest = hashlib.sha256(data).hexdigest()
        with target.open("xb") as output:
            output.write(data)
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise ValueError(f"Copied source hash mismatch: {name}")
        manifest.append({"archive_member": name, "relative_path": str(target.relative_to(baseline)).replace("\\", "/"), "bytes": row["size"], "sha256": digest, "archive_offset_data": row["offset_data"], "reasons": sorted(set(reasons[name]))})
after = archive_path.stat()
if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
    raise ValueError("Archive changed during source extraction")
report = {"prepared_at": dt.datetime.now(dt.timezone.utc).isoformat(), "archive": str(archive_path), "archive_bytes": before.st_size, "archive_mtime_ns": before.st_mtime_ns, "hdl_source_root": str(destination / "plutosdr-fw" / "hdl"), "files": manifest, "file_count": len(manifest), "source_bytes": sum(row["bytes"] for row in manifest), "archive_unchanged": True, "copied_hashes_verified": True, "source_bytes_modified": False, "vivado_started": False, "ip_upgraded": False, "board_accessed": False}
(baseline / "source-manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
dependency_report = {"project": "pzp201", "device": "xc7z020clg400-2", "required_vivado": "2021.1", "project_libraries": project_libraries, "library_graph": library_graph, "library_packaging_order": library_order, "make_dependencies": make_dependencies, "literal_input_references": literal_dependencies, "required_source_missing": missing, "expected_generated_files": ["library/" + lib + "/component.xml" for lib in library_order], "stale_xpr_and_build_cache_extracted": False, "git_metadata_extracted": False}
(record_dir / "dependency-audit.json").write_text(json.dumps(dependency_report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({key: value for key, value in report.items() if key != "files"}, ensure_ascii=False, indent=2))
print(json.dumps({"library_packaging_order": library_order, "make_dependencies_checked": len(make_dependencies), "literal_input_references": len(literal_dependencies), "required_source_missing": len(missing)}, ensure_ascii=False, indent=2))
