"""Hash the original archive without changing it; report progress."""
from pathlib import Path
import datetime as dt
import hashlib
import json
import time

path = Path(r"D:\FPGA natch\plutosdr-fw.tar")
before = path.stat()
digest = hashlib.sha256()
read = 0
start = last = time.monotonic()
with path.open("rb") as archive:
    while data := archive.read(8 * 1024**2):
        digest.update(data)
        read += len(data)
        now = time.monotonic()
        if now - last >= 15:
            print(json.dumps({"stage": "source-archive-sha256", "read_GiB": round(read / 1024**3, 3), "percent": round(100 * read / before.st_size, 1), "elapsed_s": round(now - start, 1)}), flush=True)
            last = now
after = path.stat()
if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns) or read != before.st_size:
    raise ValueError("Archive changed while hashing")
report = {"checked_at": dt.datetime.now(dt.timezone.utc).isoformat(), "archive": str(path), "bytes": read, "mtime_ns": after.st_mtime_ns, "sha256": digest.hexdigest(), "source_unchanged": True, "official_digest_available": False, "purpose": "Local provenance fingerprint; not a vendor signature or current-board firmware match", "elapsed_s": time.monotonic() - start}
Path(__file__).with_name("archive-sha256.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
