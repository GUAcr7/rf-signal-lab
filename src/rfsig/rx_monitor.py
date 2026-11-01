"""Bounded IIO RX monitoring; blocks are snapshots, never stitched into a stream.

The host clock timestamps I/O calls, not ADC samples. Hardware gaps and receive
latency are unknown. No RF configuration, BIST or TX writes are performed.
"""

from dataclasses import asdict, dataclass
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from threading import Event
from time import perf_counter

import numpy as np

from rfsig.bandwidth import occupied_bandwidth
from rfsig.iio_runtime import use_libiio
from rfsig.power import mean_iq_power, power_db
from rfsig.spectrum import power_periodogram


@dataclass(frozen=True)
class RxBlock:
    iq: np.ndarray
    host_start: float
    host_end: float
    gain_before_db: float
    gain_after_db: float


def _positive_int(value, name):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return int(value)


class MonitorSession:
    """Finite, ordered, independently analyzed blocks; a new Start is a new session."""

    def __init__(self, settings, frame_limit=120, fft_size=1024):
        self.frame_limit = _positive_int(frame_limit, "frame_limit")
        self.fft_size = _positive_int(fft_size, "fft_size")
        if self.fft_size < 4:
            raise ValueError("fft_size must be >= 4")
        self.settings = deepcopy(settings)
        fs = float(settings["sample_rate_hz"])
        bw = float(settings["rx_rf_bandwidth_hz"])
        if not np.isfinite([fs, bw]).all() or min(fs, bw) <= 0:
            raise ValueError("Sample rate and RF bandwidth must be finite and positive")
        self.sample_rate_hz = fs
        half_roi = min(bw/2, fs/2-fs/self.fft_size/2)
        self.roi = (-half_roi, half_roi)
        self.created_utc = datetime.now(timezone.utc).isoformat()
        self.started = perf_counter()
        self.state, self.error = "running", None
        self.context_released = False
        self.reference = None  # First positive-power RX block, fixed for this session.
        self.blocks, self.psds, self.bandwidths, self.powers, self.relative_db = [], [], [], [], []
        self.frequency_hz = None

    def append(self, block):
        if self.state != "running" or len(self.blocks) >= self.frame_limit:
            raise ValueError("Session is not accepting frames")
        iq = np.asarray(block.iq)
        if iq.shape != (self.fft_size,) or iq.dtype.kind != "c" or not np.isfinite(iq).all():
            raise ValueError("RX must be a finite complex vector of exactly fft_size samples")
        values = [block.host_start, block.host_end, block.gain_before_db, block.gain_after_db]
        if not np.isfinite(values).all() or block.host_end < block.host_start or block.host_start < self.started:
            raise ValueError("Invalid host timing or gain readback")
        if self.blocks and (block.host_start < self.blocks[-1].host_end or block.host_end <= self.blocks[-1].host_end):
            raise ValueError("RX calls must be ordered and non-overlapping")
        spectrum = power_periodogram(iq, self.sample_rate_hz)
        band = occupied_bandwidth(spectrum.frequency_hz, spectrum.psd, self.roi,
                                  rf_lo_hz=self.settings["rx_lo_hz"])
        power = mean_iq_power(iq)
        if self.reference is None and power > 0:
            self.reference = power
        relative = None if self.reference is None else power_db(power, self.reference)
        samples = iq.astype(np.complex128, copy=True)
        samples.flags.writeable = False
        self.blocks.append(RxBlock(samples, block.host_start, block.host_end,
                                   block.gain_before_db, block.gain_after_db))
        self.frequency_hz = spectrum.frequency_hz.copy()
        self.psds.append(spectrum.psd.copy())
        self.bandwidths.append(asdict(band))
        self.powers.append(power)
        self.relative_db.append(relative)

    def snapshot(self):
        """Copy all finite evidence; safe to hand to a GUI thread via a queue."""
        count = len(self.blocks)
        starts = np.array([b.host_start-self.started for b in self.blocks])
        ends = np.array([b.host_end-self.started for b in self.blocks])
        elapsed = float(ends[-1]) if count else 0.0
        report = {
            "schema": "rfsig.rx_monitor.v1", "created_utc": self.created_utc,
            "source_kind": "live_iio_rx_snapshots", "settings": deepcopy(self.settings),
            "state": self.state, "error": self.error, "frame_count": count,
            "receive_context_released": self.context_released,
            "frame_limit": self.frame_limit, "fft_size": self.fft_size,
            "analysis_band_hz": list(self.roi), "power_reference": self.reference,
            "power_reference_policy": "first positive-power block, fixed within this session",
            "sample_units": "unscaled raw receive counts; not volts or dBm",
            "host_elapsed_to_last_rx_seconds": elapsed,
            "observed_blocks_per_host_second": count/elapsed if elapsed > 0 else None,
            "received_sample_count": count*self.fft_size,
            "sum_of_block_sample_durations_seconds": count*self.fft_size/self.sample_rate_hz,
            "time_axis": "host I/O call timing; not ADC timestamps or contiguous sample time",
            "hardware_gap_sample_count": None, "hardware_continuity_verified": False,
            "hardware_receive_latency_verified": False, "target_detection_verified": False,
            "ai_connected": False, "gui_interaction_verified": False,
            "rf_configuration_written": False, "tx_started": False,
            "relative_power_note": "AGC gain readbacks are snapshots. Digital ratios do not measure RF input-power changes.",
            "bandwidths": deepcopy(self.bandwidths),
        }
        relative = [None if v is None or not np.isfinite(v) else v for v in self.relative_db]
        report["relative_db"] = relative
        report["relative_db_status"] = ["no_reference" if v is None else "zero_power" if not np.isfinite(v) else "finite"
                                        for v in self.relative_db]
        arrays = {
            "iq_frames": np.stack([b.iq for b in self.blocks]) if count else np.empty((0, self.fft_size), complex),
            "psd_frames": np.stack(self.psds) if count else np.empty((0, self.fft_size)),
            "frequency_hz": self.frequency_hz.copy() if count else np.empty(0),
            "host_rx_start_seconds": starts, "host_rx_end_seconds": ends,
            "gain_before_db": np.array([b.gain_before_db for b in self.blocks]),
            "gain_after_db": np.array([b.gain_after_db for b in self.blocks]),
            "mean_power": np.array(self.powers),
        }
        return report, arrays


def save_monitor_snapshot(snapshot, directory):
    report, arrays = snapshot
    if not report["frame_count"]:
        raise ValueError("No RX frame to save")
    # Round-trip copying avoids mutating the GUI/worker's original report.
    report = json.loads(json.dumps(report, allow_nan=False))
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=False)
    np.savez(target/"monitor.npz", **arrays)
    with (target/"monitor.npz").open("rb") as stream:
        report["arrays_sha256"] = hashlib.file_digest(stream, "sha256").hexdigest()
    (target/"report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+"\n",
                                      encoding="utf-8")
    return target


class P201Receiver:
    """Existing P201 raw RX only. Context, debug modes and format must match."""

    def __init__(self, dll_dir, uri="ip:192.168.2.1", fft_size=1024):
        self.dll_dir, self.uri = dll_dir, uri
        self.fft_size = _positive_int(fft_size, "fft_size")
        self.sdr = self.scope = self.phy = None
        self.cleanup_completed = False

    def _settings(self):
        return {"sample_rate_hz": int(self.sdr.sample_rate), "rx_lo_hz": int(self.sdr.rx_lo),
                "rx_rf_bandwidth_hz": int(self.sdr.rx_rf_bandwidth),
                "gain_control_mode": self.sdr.gain_control_mode_chan0,
                "rx_port": self.phy.find_channel("voltage0", False).attrs["rf_port_select"].value}

    def __enter__(self):
        self.scope = use_libiio(self.dll_dir)
        self.scope.__enter__()
        try:
            import adi
            import iio
            self.sdr = adi.ad9361(uri=self.uri)
            ctx = self.sdr.ctx
            ctx.set_timeout(3000)
            if ctx.attrs.get("hw_model") != "PUZHI PZSDR P201":
                raise RuntimeError("IIO board is not the verified P201")
            self.phy = ctx.find_device("ad9361-phy")
            rx, tx = ctx.find_device("cf-ad9361-lpc"), ctx.find_device("cf-ad9361-dds-core-lpc")
            if self.phy is None or rx is None or tx is None:
                raise RuntimeError("Missing P201 IIO control/RX/TX devices")
            modes = {k: self.phy.debug_attrs[k].value for k in ("bist_tone", "bist_prbs", "loopback")}
            scales = {ch.id: ch.attrs["scale"].value for ch in tx.channels
                      if ch.output and ch.id.startswith("altvoltage") and "scale" in ch.attrs}
            if any(v.strip() != "0" for v in modes.values()) or not scales or any(float(v) != 0 for v in scales.values()):
                raise RuntimeError("BIST/loopback or DDS is active; preserve state and stop for inspection")
            formats = {}
            for name in ("voltage0", "voltage1"):
                ch = rx.find_channel(name, False)
                if ch is None or not ch.scan_element:
                    raise RuntimeError(f"Missing RX scan channel: {name}")
                f = ch.data_format
                formats[name] = dict(bits=f.bits, storage_bits=f.length, shift=f.shift,
                                     signed=f.is_signed, big_endian=f.is_be, repeat=f.repeat)
                if (f.bits, f.length, f.shift, f.is_signed, f.is_be, f.repeat) != (12, 16, 0, True, False, 1):
                    raise RuntimeError("Unexpected P201 raw RX format")
            self.initial_settings = self._settings()
            self.initial_gain_db = float(self.sdr.rx_hardwaregain_chan0)
            self.settings = {**self.initial_settings, "board_model": ctx.attrs.get("hw_model"),
                             "initial_gain_readback_db": self.initial_gain_db,
                             "board_firmware_version": ctx.attrs.get("fw_version"),
                             "uri": self.uri, "component_channels": ["voltage0", "voltage1"],
                             "scan_format": formats, "test_modes_before": modes,
                             "dds_scales_before": scales, "iio_client_version": list(iio.version),
                             "iio_server_version": list(ctx.version)}
            self.sdr.rx_enabled_channels = [0]
            self.sdr.rx_buffer_size = self.fft_size
            # Client-side output interpretation only; does not change ADC/RF settings.
            self.sdr.rx_output_type = "raw"
            return self
        except BaseException as error:
            self.__exit__(type(error), error, error.__traceback__)
            raise

    def read(self):
        before = self._settings()
        gain_before = float(self.sdr.rx_hardwaregain_chan0)
        if before != self.initial_settings:
            raise RuntimeError("RX configuration changed; stop and start a new session")
        if before["gain_control_mode"] == "manual" and gain_before != self.initial_gain_db:
            raise RuntimeError("Manual RX gain changed before capture")
        start = perf_counter()
        iq = np.asarray(self.sdr.rx()).copy()
        end = perf_counter()
        after = self._settings()
        gain_after = float(self.sdr.rx_hardwaregain_chan0)
        if after != self.initial_settings:
            raise RuntimeError("RX configuration changed during capture")
        if after["gain_control_mode"] == "manual" and gain_after != self.initial_gain_db:
            raise RuntimeError("Manual RX gain changed during capture")
        if iq.shape != (self.fft_size,) or iq.dtype.kind != "c" or not np.isfinite(iq).all():
            raise RuntimeError("Unexpected RX sample format")
        for part in (iq.real, iq.imag):
            if np.any(part != np.round(part)) or np.any(part < -2048) or np.any(part > 2047):
                raise RuntimeError("RX counts are outside the verified signed 12-bit representation")
        return RxBlock(iq, start, end, gain_before, gain_after)

    def __exit__(self, exc_type, exc, traceback):
        failures = []
        try:
            if self.sdr is not None:
                try:
                    self.sdr.rx_destroy_buffer()
                except Exception as error:
                    failures.append(f"destroy RX buffer: {error}")
                finally:
                    try:
                        self.sdr.close()
                    except Exception as error:
                        failures.append(f"close IIO context: {error}")
                    self.sdr = None
        finally:
            self.phy = None  # IIO Device holds its parent Context; release our extra reference too.
            if self.scope is not None:
                try:
                    self.scope.__exit__(exc_type, exc, traceback)
                except Exception as error:
                    failures.append(f"release DLL scope: {error}")
                self.scope = None
        self.cleanup_completed = not failures
        if failures:
            message = "RX cleanup failed: "+"; ".join(failures)
            if exc is not None:
                exc.add_note(message)  # Preserve the original read/configuration failure.
            else:
                raise RuntimeError(message)


def run_monitor_session(receiver_factory, frame_limit=120, interval_seconds=0.1,
                        stop_event=None, on_snapshot=None):
    """Finite RX loop; release buffer/context on completion, stop or failure.

    Failures after at least one frame retain partial evidence and an error state.
    Connection failures propagate. This function itself never opens a GUI.
    """
    frame_limit = _positive_int(frame_limit, "frame_limit")
    if isinstance(interval_seconds, (bool, np.bool_)) or not np.isfinite(interval_seconds) or interval_seconds < 0:
        raise ValueError("interval_seconds must be finite and nonnegative")
    stop_event = stop_event if stop_event is not None else Event()
    session = receiver = None
    try:
        with receiver_factory() as receiver:
            session = MonitorSession(receiver.settings, frame_limit, receiver.fft_size)
            while len(session.blocks) < frame_limit and not stop_event.is_set():
                session.append(receiver.read())
                if on_snapshot is not None:
                    on_snapshot(session.snapshot())
                if len(session.blocks) < frame_limit and stop_event.wait(interval_seconds):
                    break
            session.state = "stopped" if stop_event.is_set() else "limit_reached"
    except Exception as error:
        if session is None:
            raise
        notes = "; ".join(getattr(error, "__notes__", []))
        session.state, session.error = "error", f"{type(error).__name__}: {error}"+(f"; {notes}" if notes else "")
    session.context_released = bool(getattr(receiver, "cleanup_completed", session.state != "error"))
    if on_snapshot is not None:
        on_snapshot(session.snapshot())
    return session
