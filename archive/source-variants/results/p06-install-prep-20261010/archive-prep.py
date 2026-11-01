"""Inspect a verified installer archive; extract only audited regular files."""
from pathlib import Path, PurePosixPath
import argparse
import collections
import datetime as dt
import json
import re
import shutil
import tarfile
import time


def relative_path(name):
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name:
        raise ValueError(f"Unsafe archive path: {name!r}")
    if any(":" in part for part in path.parts):
        raise ValueError(f"Drive or alternate-stream path: {name!r}")
    for part in path.parts:
        stem = part.split(".", 1)[0].upper()
        if part.endswith((".", " ")) or any(character in '<>"|?*' or ord(character) < 32 for character in part):
            raise ValueError(f"Invalid Windows path component: {name!r}")
        if stem in {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"} or re.fullmatch(r"(?:COM|LPT)[1-9¹²³]", stem):
            raise ValueError(f"Reserved Windows device path: {name!r}")
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("inventory", "extract"))
    parser.add_argument("archive", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("--destination", type=Path)
    args = parser.parse_args()
    if args.mode == "extract" and args.destination is None:
        parser.error("extract requires --destination")
    if args.mode == "extract":
        audit = json.loads(args.report.read_text(encoding="utf-8"))
        verified = json.loads(args.report.with_name("download-verification.json").read_text(encoding="utf-8-sig"))
        source_before = args.archive.stat()
        if not verified["HashMatches"] or str(args.archive.resolve()) != verified["Archive"] or source_before.st_size != verified["Bytes"]:
            raise ValueError("Archive does not match the verified download record")
        if source_before.st_mtime_ns != audit["archive_mtime_ns"] or source_before.st_size != audit["archive_bytes"]:
            raise ValueError("Archive changed after path inventory")
        if audit["unsafe_paths"] or audit["duplicates"]:
            raise ValueError("Archive path audit failed")
        for row in audit["entries"]:
            relative_path(row["name"])
        destination = args.destination.resolve()
        if destination.exists() and any(destination.iterdir()):
            raise ValueError("Extraction destination must be empty")
        destination.mkdir(parents=True, exist_ok=True)
        if shutil.disk_usage(destination).free < audit["regular_bytes"] + 10 * 1024**3:
            raise ValueError("Insufficient free space for extraction plus 10 GiB reserve")
    rows = []
    unsafe = []
    duplicates = []
    seen = set()
    groups = collections.Counter()
    counts = collections.Counter()
    total = 0
    processed = 0
    last_update = start = time.monotonic()
    with tarfile.open(args.archive, mode="r|gz") as archive:
        for member in archive:
            try:
                path = relative_path(member.name)
            except ValueError as error:
                unsafe.append(str(error))
                if args.mode == "extract":
                    raise
                continue
            key = str(path).casefold()
            if key in seen:
                duplicates.append(member.name)
            seen.add(key)
            kind = "file" if member.isfile() else "directory" if member.isdir() else "link" if member.issym() or member.islnk() else "other"
            counts[kind] += 1
            rows.append({"name": member.name, "size": member.size, "kind": kind, "link": member.linkname})
            if member.isfile():
                total += member.size
                group = "/".join(path.parts[:2])
                groups[group] += member.size
            if args.mode == "extract":
                target = destination.joinpath(*path.parts)
                target.resolve().relative_to(destination)
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                elif member.isfile():
                    if target.exists():
                        raise FileExistsError(target)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if shutil.disk_usage(destination).free < member.size + 5 * 1024**3:
                        raise ValueError("Extraction stopped to preserve 5 GiB free space")
                    source = archive.extractfile(member)
                    if source is None:
                        raise ValueError(f"Missing payload: {member.name}")
                    with source, target.open("xb") as output:
                        shutil.copyfileobj(source, output, length=4 * 1024**2)
                    if target.stat().st_size != member.size:
                        raise ValueError(f"Extracted size mismatch: {member.name}")
                    processed += member.size
                # Unix links/devices are recorded, never materialized on Windows.
            now = time.monotonic()
            if now - last_update >= 15:
                print(json.dumps({"mode": args.mode, "entries": len(rows), "file_GiB": round(total / 1024**3, 3), "written_GiB": round(processed / 1024**3, 3), "elapsed_s": round(now - start, 1)}), flush=True)
                last_update = now
    report = {"mode": args.mode, "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(), "archive": str(args.archive.resolve()), "counts": dict(counts), "regular_bytes": total, "regular_GiB": total / 1024**3, "unsafe_paths": unsafe, "duplicates": duplicates, "groups": dict(groups), "entries": rows, "elapsed_seconds": time.monotonic() - start}
    source_after = args.archive.stat()
    report["archive_bytes"] = source_after.st_size
    report["archive_mtime_ns"] = source_after.st_mtime_ns
    if args.mode == "extract":
        if source_before.st_size != source_after.st_size or source_before.st_mtime_ns != source_after.st_mtime_ns:
            raise ValueError("Archive changed during extraction")
        report["destination"] = str(destination)
        report["written_bytes"] = processed
        report["unix_links_skipped"] = counts["link"]
        report_path = args.report.with_name("extraction.json")
    else:
        report_path = args.report
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key not in {"entries", "groups"}}, ensure_ascii=False), flush=True)
    if unsafe or duplicates:
        raise ValueError("Archive audit reported unsafe paths or duplicate names")


if __name__ == "__main__":
    main()
