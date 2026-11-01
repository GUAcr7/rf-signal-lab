"""Finite offline replay and frame analysis, independent of GUI/hardware."""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from numbers import Real
from pathlib import Path

import numpy as np

from rfsig.bandwidth import OccupiedBandwidth, occupied_bandwidth
from rfsig.power import mean_iq_power, power_db
from rfsig.spectrum import PowerSpectrum, power_periodogram
from rfsig.waterfall import WaterfallHistory


@dataclass(frozen=True)
class AnalysisFrame:
    number: int  # zero-based position in this file
    start_sample: int
    time_seconds: float  # center sample time, relative to input sample zero
    iq: np.ndarray
    spectrum: PowerSpectrum
    bandwidth: OccupiedBandwidth
    mean_power: float
    relative_db: float


class OfflineReplay:
    """Each advance consumes one complete file window; no implicit looping.

    Pause freezes the cursor and history. Reset clears both. Exhaustion becomes
    finished, so old data cannot be silently presented as a fresh capture.
    """

    def __init__(self, iq, sample_rate_hz, fft_size, hop_samples,
                 analysis_band_hz, power_reference, rf_lo_hz=None, max_rows=96):
        for name, value, minimum in (("fft_size", fft_size, 4), ("hop_samples", hop_samples, 1)):
            if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)) or value < minimum:
                raise ValueError(f"{name} must be an integer >= {minimum}")
        if hop_samples > fft_size:
            raise ValueError("hop_samples must not exceed fft_size")
        array = np.asarray(iq)
        if array.ndim != 1 or array.size < fft_size or array.dtype.kind not in "biufc":
            raise ValueError("Replay needs a numeric 1D sequence with at least one complete frame")
        if not np.isfinite(array).all():
            raise ValueError("Replay samples must be finite")
        for name, value in (("sample_rate_hz", sample_rate_hz), ("power_reference", power_reference)):
            if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real) or not np.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be a positive finite scalar")
        self.iq = np.array(array, dtype=np.complex128, copy=True)
        self.iq.flags.writeable = False
        self.sample_rate_hz = float(sample_rate_hz)
        self.fft_size, self.hop_samples = int(fft_size), int(hop_samples)
        self.power_reference = float(power_reference)
        first = power_periodogram(self.iq[:fft_size], self.sample_rate_hz)
        checked = occupied_bandwidth(first.frequency_hz, first.psd, analysis_band_hz, rf_lo_hz=rf_lo_hz)
        self.analysis_band_hz = checked.analysis_band_hz
        self.rf_lo_hz = rf_lo_hz
        self.history = WaterfallHistory(first.frequency_hz, max_rows)
        self.frame_count = 1+(self.iq.size-self.fft_size)//self.hop_samples
        self.trailing_samples = int(self.iq.size-((self.frame_count-1)*self.hop_samples+self.fft_size))
        self.next_frame = 0
        self.state = "paused"
        self.latest = None

    def start(self):
        if self.state != "finished":
            self.state = "running"

    def pause(self):
        if self.state == "running":
            self.state = "paused"

    def reset(self):
        self.next_frame = 0
        self.state = "paused"
        self.latest = None
        self.history.reset()

    def advance(self):
        if self.state != "running":
            return None
        number = self.next_frame
        start = number*self.hop_samples
        samples = self.iq[start:start+self.fft_size].copy()
        spectrum = power_periodogram(samples, self.sample_rate_hz)
        band = occupied_bandwidth(spectrum.frequency_hz, spectrum.psd, self.analysis_band_hz,
                                  rf_lo_hz=self.rf_lo_hz)
        power = mean_iq_power(samples)
        frame = AnalysisFrame(number, start, (start+(self.fft_size-1)/2)/self.sample_rate_hz,
                              samples, spectrum, band, power, power_db(power, self.power_reference))
        self.history.append(spectrum.psd, frame.time_seconds)
        self.next_frame += 1
        self.latest = frame
        if self.next_frame == self.frame_count:
            self.state = "finished"
        return frame


def save_replay_snapshot(replay, directory, source):
    """Save current frame/history/config as a new record, without a screenshot.

    Relative dB is null at zero power in strict JSON, with explicit status.
    Arrays retain original finite linear PSD and I/Q; display clipping is absent.
    """
    if replay.latest is None:
        raise ValueError("No analyzed frame to save; start replay first")
    target = Path(directory)
    if target.exists():
        raise FileExistsError(target)
    frame = replay.latest
    times, frequency, history = replay.history.snapshot()
    report = {
        "schema": "rfsig.offline_analysis_snapshot.v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "hardware_contacted": False,
        "ai_connected": False,
        "state": replay.state,
        "frame_number_zero_based": frame.number,
        "frame_start_sample": frame.start_sample,
        "frame_time_seconds": frame.time_seconds,
        "source_sample_count": int(replay.iq.size),
        "complete_frame_count": replay.frame_count,
        "trailing_samples_unused": replay.trailing_samples,
        "sample_rate_hz": replay.sample_rate_hz,
        "fft_size": replay.fft_size,
        "hop_samples": replay.hop_samples,
        "window": frame.spectrum.window,
        "mean_power_unwindowed": frame.mean_power,
        "power_reference": replay.power_reference,
        "relative_db": frame.relative_db if np.isfinite(frame.relative_db) else None,
        "relative_db_status": "finite" if np.isfinite(frame.relative_db) else "zero_power",
        "bandwidth": asdict(frame.bandwidth),
        "history_rows_received": replay.history.rows_received,
        "history_rows_evicted_display_only": replay.history.rows_evicted,
        "time_axis": "input sample-index midpoint, not GUI clock or hardware timestamp",
        "target_detection_verified": False,
        "gui_interaction_verified": False,
    }
    # Validate metadata before creating any output, then never overwrite old evidence.
    json.dumps(report, ensure_ascii=False, allow_nan=False)
    target.mkdir(parents=True, exist_ok=False)
    arrays = target/"analysis.npz"
    np.savez(arrays, iq=frame.iq, frequency_hz=frequency, psd=frame.spectrum.psd,
             history_time_seconds=times, history_psd=history)
    with arrays.open("rb") as stream:
        report["analysis_sha256"] = hashlib.file_digest(stream, "sha256").hexdigest()
    (target/"report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+"\n",
                                    encoding="utf-8")
    return target
