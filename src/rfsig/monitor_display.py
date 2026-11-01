"""Archive replay and explicitly limited-window export; no device access."""

from collections import deque
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import numpy as np

from rfsig.rx_monitor import _positive_int
from rfsig.stream_monitor import load_archive_chunk, verify_stream_archive


def save_display_snapshot(snapshot, directory, *, display_mode, display_updates=0, display_replacements=0):
    report, arrays = snapshot
    if not report["retained_block_count"]:
        raise ValueError("No displayed RX block to save")
    if display_mode not in {"live", "saved_archive"}:
        raise ValueError("Unknown display mode")
    report = deepcopy(report)
    report.update({"export_schema": "rfsig.monitor_display.snapshot.v1",
                   "export_kind": "retained_window_only_not_entire_session",
                   "display_mode": display_mode, "display_updates": int(display_updates),
                   "display_queue_replacements": int(display_replacements),
                   "display_note": "Display queue replacements are not ADC dropped samples.",
                   "gui_interaction_verified": False})
    output = Path(directory)
    output.mkdir(parents=True, exist_ok=False)
    np.savez(output / "snapshot.npz", **arrays)
    report["snapshot_arrays_sha256"] = hashlib.sha256((output / "snapshot.npz").read_bytes()).hexdigest()
    (output / "snapshot.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    return output


class ArchiveReplay:
    """Replay saved host-ordered blocks with bounded history and one chunk cache.

    Original host timing is kept as evidence; UI playback speed is independent.
    It does not reconnect, retune, or run AI. Reading the archive verifies all
    committed blocks before playback starts.
    """

    def __init__(self, directory, history_frames=96):
        self.directory = Path(directory).resolve()
        self.history_frames = _positive_int(history_frames, "history_frames")
        self.verification = verify_stream_archive(self.directory)
        self.summary = json.loads((self.directory / "session.json").read_text(encoding="utf-8"))
        self.total = self.verification["verified_blocks"]
        self.reset()

    def reset(self):
        self.position, self.chunk_index, self.row_index = 0, 0, 0
        self.chunk_meta = self.chunk_arrays = None
        self.history = deque(maxlen=self.history_frames)
        self.state = "paused" if self.total else "finished"

    def start(self):
        if self.position < self.total:
            self.state = "playing"

    def pause(self):
        if self.state == "playing":
            self.state = "paused"

    def advance(self):
        if self.state != "playing":
            return self.snapshot()
        if self.chunk_arrays is None or self.row_index == self.chunk_meta["frame_count"]:
            self.chunk_index += 1
            self.chunk_meta, self.chunk_arrays = load_archive_chunk(self.directory / f"chunk-{self.chunk_index:06d}")
            self.row_index = 0
        i = self.row_index
        arrays, meta = self.chunk_arrays, self.chunk_meta
        self.history.append({"iq": arrays["iq_frames"][i], "psd": arrays["psd_frames"][i],
                             "number": int(arrays["block_numbers"][i]),
                             "start": arrays["host_rx_start_seconds"][i], "end": arrays["host_rx_end_seconds"][i],
                             "gain_before": arrays["gain_before_db"][i], "gain_after": arrays["gain_after_db"][i],
                             "power": arrays["mean_power"][i], "band": meta["bandwidths"][i],
                             "relative": meta["relative_db"][i], "relative_status": meta["relative_db_status"][i],
                             "reference": meta["power_reference"]})
        self.position += 1
        self.row_index += 1
        if self.position == self.total:
            self.state = "finished"
        return self.snapshot()

    def snapshot(self):
        report = deepcopy(self.summary)
        count, n = len(self.history), self.summary["fft_size"]
        report.update({"display_mode": "saved_archive", "playback_state": self.state,
                       "playback_position": self.position, "playback_total_blocks": self.total,
                       "retained_block_count": count, "frame_count": count,
                       "history_first_block_number": self.history[0]["number"] if count else None,
                       "history_last_block_number": self.history[-1]["number"] if count else None,
                       "history_capacity": self.history_frames,
                       "bandwidths": [deepcopy(row["band"]) for row in self.history],
                       "relative_db": [row["relative"] for row in self.history],
                       "relative_db_status": [row["relative_status"] for row in self.history]})
        if count:
            report["power_reference"] = self.history[-1]["reference"]
        keys = {"host_rx_start_seconds": "start", "host_rx_end_seconds": "end",
                "gain_before_db": "gain_before", "gain_after_db": "gain_after", "mean_power": "power",
                "block_numbers": "number"}
        arrays = {name: np.array([row[key] for row in self.history]) for name, key in keys.items()}
        arrays["iq_frames"] = np.stack([row["iq"] for row in self.history]) if count else np.empty((0, n), complex)
        arrays["psd_frames"] = np.stack([row["psd"] for row in self.history]) if count else np.empty((0, n))
        arrays["frequency_hz"] = self.chunk_arrays["frequency_hz"].copy() if count else np.empty(0)
        return report, arrays
