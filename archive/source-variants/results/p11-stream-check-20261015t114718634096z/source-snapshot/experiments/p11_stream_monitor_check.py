"""Actual P201 sustained snapshot run, bounded archive, independent readback.

RF configuration is retained. Results explicitly do not verify ADC continuity,
known-target accuracy, live AI or GUI interaction. All saved chunks are checked.
"""

import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from time import perf_counter

from rfsig.rx_monitor import P201Receiver
from rfsig.stream_monitor import run_stream_monitor, verify_stream_archive


ROOT = Path(__file__).resolve().parents[1]


def working_set_bytes():
    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                                               "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
                                               "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    process = kernel.GetCurrentProcess
    process.restype = wintypes.HANDLE
    query = ctypes.WinDLL("psapi", use_last_error=True).GetProcessMemoryInfo
    query.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    query.restype = wintypes.BOOL
    info = Counters()
    info.cb = ctypes.sizeof(info)
    if not query(process(), ctypes.byref(info), info.cb):
        raise ctypes.WinError(ctypes.get_last_error())
    return int(info.WorkingSetSize)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--libiio-dir", type=Path, default=Path(r"D:\FPGA natch\IIO-Oscilloscope-v0.18-portable\app\bin"))
    parser.add_argument("--uri", default="ip:192.168.2.1")
    parser.add_argument("--seconds", type=float, default=60)
    parser.add_argument("--max-blocks", type=int)
    parser.add_argument("--interval", type=float, default=.1)
    parser.add_argument("--history", type=int, default=96)
    parser.add_argument("--chunk", type=int, default=64)
    parser.add_argument("--quota-mib", type=int, default=512)
    args = parser.parse_args()
    out = ROOT / "results" / datetime.now(timezone.utc).strftime("p11-stream-check-%Y%m%dT%H%M%S%fZ")
    out.mkdir()
    source_names = ("src/rfsig/rx_monitor.py", "src/rfsig/stream_monitor.py", "experiments/p11_stream_monitor_check.py")
    source_hashes = {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in source_names}
    for name in source_names:
        snapshot = out / "source-snapshot" / name
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_bytes((ROOT/name).read_bytes())
    (out / "run-start.json").write_text(json.dumps({"started_utc": datetime.now(timezone.utc).isoformat(),
                                                   "requested_duration_seconds": args.seconds,
                                                   "source_code_sha256": source_hashes}, indent=2)+"\n", encoding="utf-8")
    observations, last = [], float("-inf")
    started = perf_counter()
    def observe(snapshot):
        nonlocal last
        report = snapshot[0]
        elapsed = perf_counter()-started
        if elapsed-last >= 5 or report["state"] != "running":
            item = {"host_elapsed_seconds": elapsed, "received_blocks": report["received_block_count"],
                    "retained_blocks": report["retained_block_count"],
                    "pending_blocks": report["pending_archive_block_count"],
                    "archive_chunks": report["archive_chunk_count"],
                    "working_set_bytes": working_set_bytes(), "state": report["state"]}
            observations.append(item)
            (out / "host-observations.json").write_text(json.dumps(observations, indent=2)+"\n", encoding="utf-8")
            print(json.dumps(item), flush=True)
            last = elapsed
    monitor = run_stream_monitor(lambda: P201Receiver(args.libiio_dir, args.uri), out / "session",
                                 history_frames=args.history, chunk_frames=args.chunk,
                                 max_archive_bytes=args.quota_mib*1024**2, interval_seconds=args.interval,
                                 max_duration_seconds=args.seconds, max_blocks=args.max_blocks,
                                 on_snapshot=observe)
    verification = verify_stream_archive(monitor.directory)
    verification["wall_seconds_including_connection_and_verification"] = perf_counter()-started
    verification["requested_duration_seconds"] = args.seconds
    verification["host_working_set_samples"] = observations
    verification["gui_interaction_verified"] = False
    verification["source_code_sha256"] = source_hashes
    verification["source_files_unchanged_during_run"] = all(
        hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == source_hashes[name] for name in source_names)
    (out / "verification.json").write_text(json.dumps(verification, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print("Evidence:", out, flush=True)
    print("Verification:", json.dumps({k: v for k, v in verification.items() if k != "host_working_set_samples"}), flush=True)
    if (monitor.error or not verification["archive_complete"] or not verification["receive_context_released"]
            or not verification["source_files_unchanged_during_run"]):
        raise RuntimeError("Sustained RX did not pass; inspect preserved evidence")


if __name__ == "__main__":
    main()
