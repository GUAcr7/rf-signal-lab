"""Long-running RX snapshots with bounded history and checksummed disk chunks.

No retune, transmit, BIST, firmware or hardware timestamp assumptions. The same
validated P201Receiver is used by the GUI/CLI. Disk I/O can introduce host gaps;
this is sustained snapshot monitoring, not uninterrupted ADC recording.
"""

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
from threading import Event
from time import perf_counter

import numpy as np

from rfsig.rx_monitor import MonitorSession, _positive_int


SUMMARY_RESERVE = 65536


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


class StreamMonitor:
    """One worker owns mutable state; consumers receive isolated rolling copies."""

    def __init__(self, settings, directory, fft_size=1024, history_frames=96,
                 chunk_frames=64, max_archive_bytes=512 * 1024**2,
                 source_kind="live_iio_rx_snapshots"):
        self.history_frames = _positive_int(history_frames, "history_frames")
        self.chunk_frames = _positive_int(chunk_frames, "chunk_frames")
        self.max_archive_bytes = _positive_int(max_archive_bytes, "max_archive_bytes")
        fft_size = _positive_int(fft_size, "fft_size")
        if (self.history_frames + self.chunk_frames + 2) * fft_size * 24 > 64 * 1024**2:
            raise ValueError("Configured sample/PSD storage exceeds 64 MiB; reduce history or chunk size")
        if source_kind not in {"live_iio_rx_snapshots", "synthetic_test"}:
            raise ValueError("Explicit live_iio_rx_snapshots or synthetic_test source required")
        self.source_kind = source_kind
        self.history = MonitorSession(settings, self.history_frames + 1, fft_size)
        self.directory = Path(directory).resolve()
        self.received = self.archived = self.chunks = self.archive_bytes = 0
        self.pending = []
        self.state, self.error = "running", None
        self.context_released = self.finalized = False
        self.storage_error = None
        self.max_history_observed = self.max_pending_observed = 0
        if self.max_archive_bytes < self.chunk_bound(1) + SUMMARY_RESERVE:
            raise ValueError("Archive quota is too small for one block and summary reserve")
        self.directory.mkdir(parents=True, exist_ok=False)
        self.write_summary()

    def chunk_bound(self, count):
        # Conservative upper bound for uncompressed arrays, JSON and journal.
        return count * (self.history.fft_size * 24 + 4096) + 65536

    def can_accept(self):
        return (self.archive_bytes + self.chunk_bound(len(self.pending) + 1)
                + SUMMARY_RESERVE <= self.max_archive_bytes)

    def append(self, block):
        if self.state != "running" or self.finalized:
            raise ValueError("Monitor is not accepting blocks")
        if not self.can_accept():
            raise ValueError("Archive quota would be exceeded; do not acquire another block")
        self.history.append(block)
        h = self.history
        relative = h.relative_db[-1]
        relative_status = ("no_reference" if relative is None else
                           "zero_power" if not np.isfinite(relative) else "finite")
        self.received += 1
        self.pending.append({
            "number": self.received, "block": h.blocks[-1], "psd": h.psds[-1],
            "bandwidth": deepcopy(h.bandwidths[-1]), "power": h.powers[-1],
            "relative_db": float(relative) if relative_status == "finite" else None,
            "relative_db_status": relative_status,
        })
        if len(h.blocks) > self.history_frames:
            for values in (h.blocks, h.psds, h.bandwidths, h.powers, h.relative_db):
                values.pop(0)
        self.max_history_observed = max(self.max_history_observed, len(h.blocks))
        self.max_pending_observed = max(self.max_pending_observed, len(self.pending))
        if len(self.pending) == self.chunk_frames:
            self.flush()

    def snapshot(self):
        report, arrays = self.history.snapshot()
        retained = len(self.history.blocks)
        report.update({
            "schema": "rfsig.rx_monitor.rolling.v1", "source_kind": self.source_kind,
            "state": self.state, "error": self.error, "frame_limit": None,
            "frame_count": retained, "received_block_count": self.received,
            "retained_block_count": retained,
            "history_first_block_number": self.received - retained + 1 if retained else None,
            "history_last_block_number": self.received if retained else None,
            "history_capacity": self.history_frames, "chunk_capacity": self.chunk_frames,
            "max_history_observed": self.max_history_observed,
            "max_pending_observed": self.max_pending_observed,
            "pending_archive_block_count": len(self.pending),
            "archived_block_count": self.archived, "archive_chunk_count": self.chunks,
            "archive_payload_bytes": self.archive_bytes,
            "archive_quota_bytes": self.max_archive_bytes,
            "archive_directory": str(self.directory),
            "archive_finalized": self.finalized, "storage_error": self.storage_error,
            "receive_context_released": self.context_released,
            "received_sample_count": self.received * self.history.fft_size,
            "sum_of_block_sample_durations_seconds": self.received * self.history.fft_size / self.history.sample_rate_hz,
            "rolling_evicted_blocks": self.received - retained,
            "archive_note": "Rolling eviction is not ADC loss. Chunks retain every acquired block unless storage_error is set.",
        })
        elapsed = report["host_elapsed_to_last_rx_seconds"]
        report["observed_blocks_per_host_second"] = self.received / elapsed if elapsed > 0 else None
        arrays["block_numbers"] = np.arange(self.received - retained + 1, self.received + 1, dtype=np.int64)
        return report, arrays

    def write_summary(self):
        report, _ = self.snapshot()
        # Keep the summary small; detailed per-block statistics live in chunks.
        for key in ("bandwidths", "relative_db", "relative_db_status"):
            report.pop(key)
        payload = _json_bytes(report)
        if len(payload) > SUMMARY_RESERVE:
            raise ValueError("Summary exceeded its reserved disk budget")
        temporary = self.directory / "session.json.tmp"
        temporary.write_bytes(payload)
        temporary.replace(self.directory / "session.json")

    def flush(self):
        if not self.pending:
            return
        records = self.pending
        h = self.history
        arrays = {
            "iq_frames": np.stack([r["block"].iq for r in records]),
            "psd_frames": np.stack([r["psd"] for r in records]),
            "frequency_hz": h.frequency_hz.copy(),
            "host_rx_start_seconds": np.array([r["block"].host_start - h.started for r in records]),
            "host_rx_end_seconds": np.array([r["block"].host_end - h.started for r in records]),
            "gain_before_db": np.array([r["block"].gain_before_db for r in records]),
            "gain_after_db": np.array([r["block"].gain_after_db for r in records]),
            "mean_power": np.array([r["power"] for r in records]),
            "block_numbers": np.array([r["number"] for r in records], dtype=np.int64),
        }
        buffer = io.BytesIO()
        np.savez(buffer, **arrays)
        payload = buffer.getvalue()
        report = {
            "schema": "rfsig.rx_archive.chunk.v1", "source_kind": self.source_kind,
            "session_created_utc": h.created_utc, "settings": deepcopy(h.settings),
            "frame_count": len(records), "fft_size": h.fft_size,
            "first_block_number": records[0]["number"], "last_block_number": records[-1]["number"],
            "analysis_band_hz": list(h.roi), "power_reference": h.reference,
            "power_reference_policy": "first positive-power block, fixed within the whole session",
            "bandwidths": [r["bandwidth"] for r in records],
            "relative_db": [r["relative_db"] for r in records],
            "relative_db_status": [r["relative_db_status"] for r in records],
            "arrays_sha256": hashlib.sha256(payload).hexdigest(),
            "hardware_continuity_verified": False, "target_detection_verified": False,
            "ai_connected": False, "rf_configuration_written": False, "tx_started": False,
        }
        metadata = _json_bytes(report)
        name = f"chunk-{self.chunks + 1:06d}"
        journal = _json_bytes({"chunk": name, "first": records[0]["number"],
                               "last": records[-1]["number"], "arrays_sha256": report["arrays_sha256"]})
        # Journal entries occupy one line, so an interrupted tail is detectable.
        journal = (json.dumps(json.loads(journal), separators=(",", ":")) + "\n").encode("utf-8")
        size = len(payload) + len(metadata) + len(journal)
        if self.archive_bytes + size + SUMMARY_RESERVE > self.max_archive_bytes:
            raise OSError("Archive quota exhausted before chunk commit")
        target = self.directory / name
        try:
            target.mkdir(exist_ok=False)
            with (target / "monitor.npz").open("xb") as stream:
                stream.write(payload)
            with (target / "report.json").open("xb") as stream:
                stream.write(metadata)
            with (self.directory / "chunks.jsonl").open("ab") as stream:
                stream.write(journal)
            self.archived += len(records)
            self.chunks += 1
            self.archive_bytes += size
            self.pending = []
            self.write_summary()
        except Exception as error:
            self.storage_error = f"{type(error).__name__}: {error}"
            raise


def run_stream_monitor(receiver_factory, directory, *, history_frames=96, chunk_frames=64,
                       max_archive_bytes=512 * 1024**2, interval_seconds=0.1,
                       stop_event=None, on_snapshot=None, max_blocks=None,
                       max_duration_seconds=None, source_kind="live_iio_rx_snapshots"):
    """Run until Stop, time/block limit, disk budget or error; release RX then flush.

    New archive directories are exclusive. Errors retain chunks and a final error
    report. Display updates are replaceable snapshots; ADC gaps remain unknown.
    """
    if isinstance(interval_seconds, (bool, np.bool_)) or not np.isfinite(interval_seconds) or interval_seconds < 0:
        raise ValueError("interval_seconds must be finite and nonnegative")
    if max_blocks is not None:
        max_blocks = _positive_int(max_blocks, "max_blocks")
    if max_duration_seconds is not None:
        if (isinstance(max_duration_seconds, (bool, np.bool_)) or
                not np.isfinite(max_duration_seconds) or max_duration_seconds <= 0):
            raise ValueError("max_duration_seconds must be finite and positive")
    stop = stop_event if stop_event is not None else Event()
    monitor = receiver = None
    try:
        with receiver_factory() as receiver:
            monitor = StreamMonitor(receiver.settings, directory, receiver.fft_size,
                                    history_frames, chunk_frames, max_archive_bytes, source_kind)
            while True:
                if stop.is_set():
                    monitor.state = "stopped"
                    break
                if max_blocks is not None and monitor.received >= max_blocks:
                    monitor.state = "block_limit"
                    break
                if max_duration_seconds is not None and perf_counter() - monitor.history.started >= max_duration_seconds:
                    monitor.state = "time_limit"
                    break
                if not monitor.can_accept():
                    monitor.state = "archive_limit"
                    break
                monitor.append(receiver.read())
                if on_snapshot is not None:
                    on_snapshot(monitor.snapshot())
                stop.wait(interval_seconds)
    except Exception as error:
        if monitor is None:
            raise
        notes = "; ".join(getattr(error, "__notes__", []))
        monitor.state, monitor.error = "error", f"{type(error).__name__}: {error}" + (f"; {notes}" if notes else "")
    except KeyboardInterrupt:
        if monitor is None:
            raise
        monitor.state = "interrupted"
    finally:
        if monitor is not None:
            monitor.context_released = bool(getattr(receiver, "cleanup_completed", False))
            try:
                if monitor.storage_error is None:
                    monitor.flush()
                monitor.finalized = monitor.storage_error is None and monitor.archived == monitor.received
                monitor.write_summary()
            except Exception as error:
                monitor.state = "error"
                monitor.error = (monitor.error + "; " if monitor.error else "") + f"Finalize {type(error).__name__}: {error}"
                monitor.finalized = False
                try:
                    monitor.write_summary()
                except Exception:
                    pass  # Preserve the original storage failure for the caller.
            if on_snapshot is not None:
                on_snapshot(monitor.snapshot())
    return monitor


def load_archive_chunk(directory):
    """Read one committed chunk with hash, schema and shape checks; no hardware."""
    directory = Path(directory)
    report = json.loads((directory / "report.json").read_text(encoding="utf-8"))
    if report["schema"] != "rfsig.rx_archive.chunk.v1":
        raise ValueError("Unsupported archive chunk schema")
    payload = (directory / "monitor.npz").read_bytes()
    if hashlib.sha256(payload).hexdigest() != report["arrays_sha256"]:
        raise ValueError("Archive array hash mismatch")
    with np.load(io.BytesIO(payload), allow_pickle=False) as source:
        arrays = {name: source[name].copy() for name in source.files}
    count, n = report["frame_count"], report["fft_size"]
    if arrays["iq_frames"].shape != (count, n) or arrays["psd_frames"].shape != (count, n):
        raise ValueError("Archive dimensions differ from metadata")
    if not np.array_equal(arrays["block_numbers"], np.arange(report["first_block_number"], report["last_block_number"] + 1)):
        raise ValueError("Archive block numbering is inconsistent")
    return report, arrays


def verify_stream_archive(directory):
    """Recompute every chunk independently; sequence is host order, never ADC time.

    Verification is read-only and streaming over chunks. It also works after a
    partial RX error, but refuses to call an unfinalized/partially written archive
    complete. The returned report always distinguishes completeness and health.
    """
    directory = Path(directory)
    summary = json.loads((directory / "session.json").read_text(encoding="utf-8"))
    if summary["schema"] != "rfsig.rx_monitor.rolling.v1":
        raise ValueError("Unsupported session schema")
    journal_path = directory / "chunks.jsonl"
    entries = [] if not journal_path.exists() else [json.loads(line) for line in journal_path.read_text(encoding="utf-8").splitlines()]
    if len(entries) != summary["archive_chunk_count"]:
        raise ValueError("Archive journal count differs from summary")
    expected_names = [f"chunk-{i + 1:06d}" for i in range(len(entries))]
    if [e["chunk"] for e in entries] != expected_names:
        raise ValueError("Archive journal sequence is invalid")
    if sorted(p.name for p in directory.glob("chunk-*")) != expected_names:
        raise ValueError("Uncommitted or missing archive directory")
    total, previous_end, reference = 0, 0.0, None
    max_psd_error = max_roi_error = 0.0
    unique_hashes = set()
    for entry in entries:
        meta, arrays = load_archive_chunk(directory / entry["chunk"])
        if meta["settings"] != summary["settings"] or meta["source_kind"] != summary["source_kind"]:
            raise ValueError("Chunk settings/source differ from session")
        if (meta["first_block_number"] != total + 1 or entry["first"] != total + 1
                or entry["last"] != meta["last_block_number"] or entry["arrays_sha256"] != meta["arrays_sha256"]):
            raise ValueError("Chunk numbering or journal hash differs")
        iq, psd, freq = arrays["iq_frames"], arrays["psd_frames"], arrays["frequency_hz"]
        n, fs = meta["fft_size"], float(meta["settings"]["sample_rate_hz"])
        if not np.isfinite(iq).all() or not np.isfinite(psd).all() or np.any(psd < 0):
            raise ValueError("Invalid saved numerical data")
        if summary["source_kind"] == "live_iio_rx_snapshots":
            for part in (iq.real, iq.imag):
                if np.any(part != np.rint(part)) or np.any(part < -2048) or np.any(part > 2047):
                    raise ValueError("Saved RX counts are not signed 12-bit integers")
        np.testing.assert_array_equal(freq, np.fft.fftshift(np.fft.fftfreq(n, d=1/fs)))
        window = .5 - .5 * np.cos(2 * np.pi * np.arange(n) / n)
        expected = np.abs(np.fft.fftshift(np.fft.fft(iq * window, axis=1), axes=1))**2 / (fs * np.sum(window**2))
        np.testing.assert_allclose(psd, expected, rtol=3e-15, atol=1e-18)
        max_psd_error = max(max_psd_error, float(np.max(np.abs(psd - expected))))
        powers = np.mean(iq.real**2 + iq.imag**2, axis=1)
        np.testing.assert_allclose(arrays["mean_power"], powers, rtol=1e-13, atol=1e-13)
        starts, ends = arrays["host_rx_start_seconds"], arrays["host_rx_end_seconds"]
        for i, (start, end, power) in enumerate(zip(starts, ends, powers, strict=True)):
            if not np.isfinite([start, end, arrays["gain_before_db"][i], arrays["gain_after_db"][i]]).all():
                raise ValueError("Nonfinite timing/gain metadata")
            if start < previous_end or end < start or (total + i > 0 and end <= previous_end):
                raise ValueError("Host receive calls overlap or are unordered")
            previous_end = float(end)
            if reference is None and power > 0:
                reference = float(power)
            status = "no_reference" if reference is None else "zero_power" if power == 0 else "finite"
            if meta["relative_db_status"][i] != status:
                raise ValueError("Relative power status differs from samples")
            if status == "finite":
                np.testing.assert_allclose(meta["relative_db"][i], 10*np.log10(power/reference), atol=1e-12, rtol=1e-12)
            elif meta["relative_db"][i] is not None:
                raise ValueError("Undefined relative power must be explicit null")
            # A separate piecewise-density CDF, without occupied_bandwidth().
            low, high = meta["analysis_band_hz"]
            df = fs / n
            left, right = np.maximum(freq - df/2, low), np.minimum(freq + df/2, high)
            mass = psd[i] * np.maximum(right-left, 0)
            active = np.flatnonzero(mass > 0)
            band = meta["bandwidths"][i]
            if active.size:
                cumulative = np.cumsum(mass[active])
                edges = []
                for q in (.005, .995):
                    target = q * cumulative[-1]
                    j = min(int(np.searchsorted(cumulative, target, side="left")), len(active)-1)
                    cell = active[j]
                    previous = cumulative[j-1] if j else 0
                    edges.append(float(left[cell] + (target-previous)/mass[cell] * (right[cell]-left[cell])))
                expected_values = (edges[0], edges[1], edges[1]-edges[0], (edges[0]+edges[1])/2)
                if band["status"] != "ok":
                    raise ValueError("Positive PSD region has no interval")
                for key, value in zip(("lower_hz", "upper_hz", "bandwidth_hz", "center_baseband_hz"), expected_values, strict=True):
                    error = abs(band[key]-value)
                    max_roi_error = max(max_roi_error, error)
                    np.testing.assert_allclose(band[key], value, atol=1e-6, rtol=1e-12)
            elif band["status"] != "no_effective_power":
                raise ValueError("Zero PSD fabricated a target interval")
            unique_hashes.add(hashlib.sha256(iq[i].tobytes()).hexdigest())
        if meta["power_reference"] is None:
            if reference is not None:
                raise ValueError("Missing positive-power reference")
        else:
            np.testing.assert_allclose(meta["power_reference"], reference, rtol=1e-13, atol=1e-13)
        total += len(iq)
    if total != summary["archived_block_count"]:
        raise ValueError("Saved block total differs from session")
    if summary["archive_finalized"] and (total != summary["received_block_count"] or summary["pending_archive_block_count"]):
        raise ValueError("Finalized archive omits accepted blocks")
    complete = summary["archive_finalized"] and total == summary["received_block_count"]
    file_bytes = sum(p.stat().st_size for p in directory.rglob("*") if p.is_file())
    if file_bytes > summary["archive_quota_bytes"]:
        raise ValueError("Archive exceeds configured quota")
    return {"schema": "rfsig.rx_archive.verification.v1", "directory": str(directory.resolve()),
            "verified_utc": datetime.now(timezone.utc).isoformat(),
            "source_kind": summary["source_kind"], "state": summary["state"],
            "error": summary["error"], "received_blocks": summary["received_block_count"],
            "verified_blocks": total, "unique_block_count": len(unique_hashes),
            "chunk_count": len(entries), "archive_complete": complete,
            "receive_context_released": summary["receive_context_released"],
            "all_saved_blocks_independently_recomputed": True,
            "max_psd_absolute_error": max_psd_error, "max_roi_edge_error_hz": max_roi_error,
            "archive_actual_bytes": file_bytes, "archive_quota_bytes": summary["archive_quota_bytes"],
            "retained_blocks": summary["retained_block_count"],
            "history_capacity": summary["history_capacity"],
            "max_history_observed": summary["max_history_observed"],
            "max_pending_observed": summary["max_pending_observed"],
            "hardware_continuity_verified": False, "target_detection_verified": False,
            "ai_connected": False, "rf_configuration_written": False, "tx_started": False}
