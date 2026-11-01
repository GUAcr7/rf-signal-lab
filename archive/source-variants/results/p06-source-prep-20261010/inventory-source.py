"""Read-only tar metadata inventory and small source-entry excerpts."""
from pathlib import Path
import collections
import datetime as dt
import json
import tarfile
import time

archive_path = Path(r"D:\FPGA natch\plutosdr-fw.tar")
output_dir = Path(__file__).resolve().parent
before = archive_path.stat()
entries = []
counts = collections.Counter()
groups = collections.Counter()
snippets = {}
wanted = {
    "plutosdr-fw/hdl/projects/pzp201/Makefile",
    "plutosdr-fw/hdl/projects/pzp201/system_project.tcl",
    "plutosdr-fw/hdl/projects/pzp201/system_bd.tcl",
    "plutosdr-fw/hdl/projects/scripts/adi_env.tcl",
    "plutosdr-fw/hdl/Makefile",
    "plutosdr-fw/hdl/README.md",
    "plutosdr-fw/.gitmodules",
    "plutosdr-fw/Makefile",
    "plutosdr-fw/hdl/.git",
}
start = last = time.monotonic()
total_members = 0
with tarfile.open(archive_path, mode="r:") as archive:
    for member in archive:
        total_members += 1
        if member.name.startswith("plutosdr-fw/hdl/"):
            kind = "file" if member.isfile() else "directory" if member.isdir() else "link" if member.issym() or member.islnk() else "other"
            entries.append({"name": member.name, "size": member.size, "kind": kind, "link": member.linkname, "offset_data": member.offset_data})
            counts[kind] += 1
            if member.isfile():
                groups["/".join(member.name.split("/")[:4])] += member.size
        if member.name in wanted and member.isfile() and member.size <= 128 * 1024:
            source = archive.extractfile(member)
            snippets[member.name] = source.read().decode("utf-8", errors="replace")
        now = time.monotonic()
        if now - last >= 15:
            print(json.dumps({"stage": "tar-metadata", "entries_scanned": total_members, "hdl_entries": len(entries), "elapsed_s": round(now - start, 1)}), flush=True)
            last = now
after = archive_path.stat()
if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
    raise ValueError("Source archive changed during inventory")
report = {"checked_at": dt.datetime.now(dt.timezone.utc).isoformat(), "archive": str(archive_path), "archive_bytes": after.st_size, "archive_mtime_ns": after.st_mtime_ns, "total_archive_members": total_members, "hdl_counts": dict(counts), "hdl_groups_bytes": dict(groups), "entries": entries, "source_snippets": snippets, "elapsed_s": time.monotonic() - start}
(output_dir / "archive-source-index.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({key: value for key, value in report.items() if key not in {"entries", "source_snippets", "hdl_groups_bytes"}}, ensure_ascii=False, indent=2))
for name, content in snippets.items():
    print(f"SOURCE {name}\n{content}")
