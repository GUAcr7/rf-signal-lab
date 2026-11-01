"""P05 offline viewer. GUI is opened only when the user runs this file.

--headless verifies file replay/render/export without creating a GUI or IIO
connection. No RF, model inference or board configuration is performed.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import sys
from time import perf_counter

import numpy as np

from rfsig.iq_recording import load_iq_record
from rfsig.power import mean_iq_power
from rfsig.replay_analysis import OfflineReplay, save_replay_snapshot
from rfsig.waterfall import waterfall_periodogram


ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT/"results"/"p05a-waterfall-20261003T120810649553Z"
RECORD = ROOT/"results"/"p02-20261003T100526764044Z"


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def load_source(args):
    if args.source == "demo":
        report = json.loads((args.demo/"report.json").read_text(encoding="utf-8"))
        arrays_path = args.demo/"waterfall.npz"
        digest = sha256(arrays_path)
        if digest != report["result_sha256"]["waterfall.npz"]:
            raise ValueError("Demo file hash differs from its experimental report")
        with np.load(arrays_path, allow_pickle=False) as saved:
            iq = saved["synthetic_iq"].copy()
        cfg = report["synthetic"]
        if iq.ndim != 1 or iq.size != cfg["sample_count"]:
            raise ValueError("Demo sample count/shape differs from its report")
        source = {"kind": "synthetic_saved", "name": "SIMULATED FILE | NOT LIVE RF",
                  "input_directory": str(args.demo.resolve()), "sample_container_sha256": digest,
                  "sample_units": "normalized units", "modulation_label": None,
                  "reference_note": "fixed P_ref = 0.25 normalized units squared"}
        replay = OfflineReplay(iq, cfg["sample_rate_hz"], cfg["fft_size"], cfg["hop_samples"],
                               (-400_000, 400_000), 0.25)
    else:
        iq, meta = load_iq_record(args.record)
        before, after = meta["settings_before"], meta["settings_after"]
        for key in ("sample_rate_hz", "rx_lo_hz", "rx_rf_bandwidth_hz"):
            if before[key] != after[key]:
                raise ValueError(f"Saved configuration changed during capture: {key}")
        if meta.get("sample_units") != "unscaled raw receive counts; not volts or dBm":
            raise ValueError("Expected unscaled P02 raw receive counts")
        reference = mean_iq_power(iq)  # Fixed whole-record digital reference, not RF calibration.
        if reference <= 0:
            raise ValueError("Saved record must have positive power for its fixed digital reference")
        half_roi = float(before["rx_rf_bandwidth_hz"])/2
        source = {"kind": "saved_real_unknown", "name": "SAVED REAL RX | NOT LIVE | TARGET UNKNOWN",
                  "input_directory": str(args.record.resolve()), "sample_sha256": meta["sample_sha256"],
                  "capture_id": meta["capture_id"], "capture_end_utc": meta["capture_end_utc"],
                  "sample_units": "raw counts", "modulation_label": None,
                  "gain_control_mode": before["gain_control_mode"],
                  "rx_rf_bandwidth_hz": before["rx_rf_bandwidth_hz"],
                  "reference_note": "fixed P_ref = mean power of this entire saved record; not dBm"}
        # Preserve full 1024-point frequency resolution. One old short record -> one frame.
        replay = OfflineReplay(iq, before["sample_rate_hz"], 1024, 1024, (-half_roi, half_roi),
                               reference, rf_lo_hz=before["rx_lo_hz"])
    return replay, source


class ReplayView:
    def __init__(self, replay, source, interactive):
        import matplotlib.pyplot as plt
        from matplotlib.widgets import Button

        self.replay, self.source = replay, source
        self.interactive = interactive
        self.color_limits = (-105, -30) if source["kind"] == "synthetic_saved" else (-100, -25)
        self.source["display_policy"] = {"psd_log_floor_for_display_only": 1e-16,
                                         "waterfall_db_limits_fixed": list(self.color_limits),
                                         "demo_time_plot_first_samples": 64}
        self.fig = plt.figure(figsize=(12.8, 8.6), layout=None)
        self.fig.canvas.manager.set_window_title("RF signal analysis - OFFLINE FILE REPLAY")
        grid = self.fig.add_gridspec(2, 2, left=0.075, right=0.925, bottom=0.235, top=0.87,
                                    wspace=0.28, hspace=0.45)
        self.time_ax = self.fig.add_subplot(grid[0, 0])
        self.info_ax = self.fig.add_subplot(grid[0, 1])
        self.spec_ax = self.fig.add_subplot(grid[1, 0])
        self.water_ax = self.fig.add_subplot(grid[1, 1])
        self.color_ax = self.fig.add_axes((0.939, 0.235, 0.013, 0.259))
        self.info_ax.axis("off")
        self.fig.suptitle(source["name"], y=0.97, fontsize=15, fontweight="bold")
        self.fig.text(0.075, 0.91, "File sample time and UI playback speed are independent. AI: NOT CONNECTED.", fontsize=10)
        self.note = self.fig.text(0.075, 0.153, "", fontsize=9, va="top")
        self.status_text = self.fig.text(0.075, 0.019, "Ready. Click Start to replay a finite file.", fontsize=9)
        self.buttons = []
        for left, label, callback in ((0.17, "Start / Pause", self.toggle),
                                      (0.43, "Reset", self.reset), (0.69, "Save", self.save)):
            axis = self.fig.add_axes((left, 0.055, 0.17, 0.045))
            button = Button(axis, label)
            button.on_clicked(callback)
            self.buttons.append(button)
        self.timer = self.fig.canvas.new_timer(interval=100)
        self.timer.add_callback(self.step)
        self.fig.canvas.mpl_connect("close_event", lambda event: self.timer.stop())
        self.draw()

    def draw(self):
        for axis in (self.time_ax, self.spec_ax, self.water_ax):
            axis.clear()
        self.info_ax.clear()
        self.info_ax.axis("off")
        self.color_ax.clear()
        self.color_ax.set_visible(False)
        replay, frame = self.replay, self.replay.latest
        frequency_scale = 1e6 if replay.sample_rate_hz > 10e6 else 1e3
        frequency_unit = "MHz" if frequency_scale == 1e6 else "kHz"
        self.time_ax.set(xlabel="Time within this frame (us)", ylabel=f"I / Q ({self.source['sample_units']})",
                         title="I/Q time domain")
        self.spec_ax.set(xlabel=f"Baseband frequency offset ({frequency_unit})",
                         ylabel="PSD (dB re 1 input unit^2/Hz)", title="Spectrum | Hann window")
        self.water_ax.set(xlabel=f"Baseband frequency offset ({frequency_unit})",
                          ylabel="Source sample time (ms)", title="Waterfall | latest history rows")
        self.time_ax.grid(alpha=0.25)
        self.spec_ax.grid(alpha=0.25)
        f = replay.history.snapshot()[1]
        self.spec_ax.set_xlim(f[0]/frequency_scale, f[-1]/frequency_scale)
        config = (f"State: {replay.state.upper()}    Frame: {replay.next_frame}/{replay.frame_count}\n"
                  f"Fs: {replay.sample_rate_hz/1e6:g} MS/s\n"
                  f"FFT: {replay.fft_size}    Hop: {replay.hop_samples}\n"
                  f"Bin spacing: {replay.sample_rate_hz/replay.fft_size:g} Hz\n"
                  f"ROI: [{replay.analysis_band_hz[0]/frequency_scale:g}, "
                  f"{replay.analysis_band_hz[1]/frequency_scale:g}] {frequency_unit}\n")
        if frame is not None:
            visible = min(64, replay.fft_size) if self.source["kind"] == "synthetic_saved" else replay.fft_size
            t = np.arange(visible)/replay.sample_rate_hz*1e6
            self.time_ax.plot(t, frame.iq.real[:visible], lw=0.8, label="I")
            self.time_ax.plot(t, frame.iq.imag[:visible], lw=0.8, label="Q")
            self.time_ax.set_title(f"I/Q time domain | first {visible}/{replay.fft_size} samples", fontsize=10)
            self.time_ax.legend(loc="upper right", fontsize=8)
            density_db = 10*np.log10(np.maximum(frame.spectrum.psd, 1e-16))
            self.spec_ax.plot(frame.spectrum.frequency_hz/frequency_scale, density_db, lw=0.8)
            band = frame.bandwidth
            db_text = "-inf (zero power)" if not np.isfinite(frame.relative_db) else f"{frame.relative_db:+.3f} dB"
            config += (f"Source time: {frame.time_seconds*1e3:.6f} ms\n"
                       f"Mean I^2+Q^2: {frame.mean_power:.6g}\n"
                       f"Relative power: {db_text}\n"
                       f"Fixed P_ref: {replay.power_reference:.6g}\n")
            if band.status == "ok":
                self.spec_ax.axvspan(band.lower_hz/frequency_scale, band.upper_hz/frequency_scale,
                                    alpha=0.2, color="orange")
                self.spec_ax.axvline(band.center_baseband_hz/frequency_scale, color="red", ls="--", lw=1)
                config += (f"99% region width: {band.bandwidth_hz/frequency_scale:.6g} {frequency_unit}\n"
                           f"Region midpoint: {band.center_baseband_hz/frequency_scale:.6g} {frequency_unit}\n")
                if band.center_rf_hz is not None:
                    config += f"LO + midpoint: {band.center_rf_hz/1e6:.6f} MHz*\n"
            else:
                config += f"Bandwidth: N/A ({band.status})\n"
            times, frequency, density = replay.history.snapshot()
            db = 10*np.log10(np.maximum(density, 1e-16))
            step = replay.hop_samples/replay.sample_rate_hz
            width = replay.sample_rate_hz/replay.fft_size
            # Uniform replay times allow imshow, including the single-real-frame case.
            mesh = self.water_ax.imshow(db, origin="lower", aspect="auto", cmap="viridis",
                                 vmin=self.color_limits[0], vmax=self.color_limits[1],
                                 extent=((frequency[0]-width/2)/frequency_scale,
                                         (frequency[-1]+width/2)/frequency_scale,
                                         (times[0]-step/2)*1e3, (times[-1]+step/2)*1e3))
            self.color_ax.set_visible(True)
            colorbar = self.fig.colorbar(mesh, cax=self.color_ax)
            colorbar.ax.tick_params(labelsize=8)
            self.water_ax.set_title(f"Waterfall | {len(times)} rows | color = PSD dB", fontsize=10)
        else:
            for axis in (self.time_ax, self.spec_ax, self.water_ax):
                axis.text(0.5, 0.5, "Click Start", transform=axis.transAxes, ha="center")
        self.info_ax.text(0, 1, config, va="top", fontsize=10, family="monospace", linespacing=1.3)
        note = ("99% interval describes the selected PSD region; it does not detect a known target. "
                "AI has no class/confidence output.\n"+self.source["reference_note"])
        if self.source["kind"] == "saved_real_unknown":
            note += "\n* Unknown RF input + saved AGC: midpoint is not verified target center; source is one old 33 us record."
        else:
            note += "\n10 frames/s playback is a requested GUI timer rate, not measured RF throughput."
        self.note.set_text(note)
        self.fig.canvas.draw_idle()

    def toggle(self, event=None):
        if self.replay.state == "running":
            self.timer.stop()
            self.replay.pause()
            self.status_text.set_text("Paused at the same file position. Start resumes.")
        elif self.replay.state == "finished":
            self.status_text.set_text("End of file. Reset, then Start to replay the same saved data.")
        else:
            self.replay.start()
            if self.interactive:
                self.timer.start()
            self.status_text.set_text("Replaying a saved file. No hardware is connected by this viewer.")
        self.draw()

    def step(self):
        # Return None: Matplotlib removes timer callbacks if they return False/0.
        frame = self.replay.advance()
        if frame is not None:
            self.draw()
        if self.replay.state == "finished":
            self.timer.stop()
            self.status_text.set_text("End of file. Reset, then Start to replay the same saved data.")
            self.fig.canvas.draw_idle()

    def reset(self, event=None):
        self.timer.stop()
        self.replay.reset()
        self.status_text.set_text("Reset cleared the old frame and waterfall. Click Start.")
        self.draw()

    def export(self, output=None):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        output = output or ROOT/"results"/f"p05-viewer-{stamp}"
        target = save_replay_snapshot(self.replay, output, self.source)
        self.status_text.set_text(f"Saved: {target.name} (PNG + NPZ + JSON)")
        self.fig.savefig(target/"viewer.png", dpi=120)
        return target

    def save(self, event=None):
        try:
            target = self.export()
        except Exception as error:
            self.status_text.set_text(f"Save failed: {error}")
            print(f"Save failed: {error}", file=sys.stderr)
        else:
            self.status_text.set_text(f"Saved: {target.name} (PNG + NPZ + JSON)")
            print(f"Saved evidence: {target}", flush=True)
        self.fig.canvas.draw_idle()


def headless_check(view, output):
    replay = view.replay
    expected = waterfall_periodogram(replay.iq, replay.sample_rate_hz, replay.fft_size, replay.hop_samples)
    view.toggle()  # Invoke callback code; no real GUI event is claimed.
    begin = perf_counter()
    first = replay.advance()
    frame_times = [(perf_counter()-begin)*1000]
    pause_resume_verified = False
    if replay.state == "running":
        view.toggle()
        cursor = replay.next_frame
        if replay.advance() is not None or replay.next_frame != cursor:
            raise RuntimeError("Pause did not freeze cursor")
        view.toggle()
        pause_resume_verified = True
    frames = [first]
    while replay.state == "running":
        begin = perf_counter()
        frames.append(replay.advance())
        frame_times.append((perf_counter()-begin)*1000)
    np.testing.assert_array_equal(np.stack([x.spectrum.psd for x in frames]), expected.psd)
    np.testing.assert_array_equal([x.time_seconds for x in frames], expected.time_seconds)
    replay.start()
    if replay.advance() is not None or replay.next_frame != replay.frame_count:
        raise RuntimeError("Finished file unexpectedly looped")
    view.reset()
    if replay.latest is not None or replay.history.rows_received:
        raise RuntimeError("Reset did not clear old results")
    view.toggle()
    again = replay.advance()
    np.testing.assert_array_equal(first.iq, again.iq)
    np.testing.assert_array_equal(first.spectrum.psd, again.spectrum.psd)
    # A demonstration snapshot with all three tone regions visible in 96 rows.
    for _ in range(min(134, replay.frame_count-1)):
        replay.advance()
    replay.pause()
    view.draw()
    target = view.export(output)
    with np.load(target/"analysis.npz", allow_pickle=False) as arrays:
        np.testing.assert_array_equal(arrays["iq"], replay.latest.iq)
        np.testing.assert_array_equal(arrays["history_psd"], replay.history.snapshot()[2])
    validation = {
        "scope": "headless rendering and callback/controller invocation; not actual GUI events",
        "source": view.source,
        "all_complete_frames_match_batch_psd_and_sample_times": True,
        "complete_frames_checked": len(frames),
        "pause_resume_logic_verified": pause_resume_verified,
        "pause_resume_note": "Single-frame records cannot verify multi-frame pause/resume" if not pause_resume_verified else "Direct callback/controller invocation only",
        "reset_and_end_of_file_logic_verified": True,
        "save_reload_arrays_exact_match": True,
        "headless_render_completed": True,
        "gui_window_launch_verified": False,
        "gui_button_clicks_verified": False,
        "continuous_hardware_capture_verified": False,
        "hardware_contacted": False,
        "ai_connected": False,
        "runtime": {"python": platform.python_version(), "numpy": np.__version__, "os": platform.platform()},
        "desktop_processing_timing": {
            "frames_timed": len(frame_times), "warmup_excluded": False,
            "median_ms": float(np.median(frame_times)), "max_ms": max(frame_times),
            "scope": "one replay advance: FFT, bandwidth, power, history; excludes loading, plot and GUI refresh",
            "hardware_or_realtime_throughput_measurement": False},
        "source_code_sha256": {str(path.relative_to(ROOT)): sha256(path) for path in
                               (Path(__file__), ROOT/"src/rfsig/replay_analysis.py")},
        "output_sha256": {name: sha256(target/name) for name in ("analysis.npz", "report.json", "viewer.png")},
    }
    (target/"headless-validation.json").write_text(json.dumps(validation, ensure_ascii=False, indent=2, allow_nan=False)+"\n",
                                                  encoding="utf-8")
    print(json.dumps({"output": str(target), "frames_checked": len(frames),
                      "headless_passed": True, "GUI": "pending user launch/clicks"}, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=("demo", "record"), default="demo")
    parser.add_argument("--demo", type=Path, default=DEMO)
    parser.add_argument("--record", type=Path, default=RECORD)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--output", type=Path, help="New headless evidence directory")
    args = parser.parse_args()
    import matplotlib
    matplotlib.use("Agg" if args.headless else "TkAgg")
    import matplotlib.pyplot as plt
    replay, source = load_source(args)
    print(f"Source: {source['name']}\nComplete frames: {replay.frame_count}\nAI: not connected", flush=True)
    view = ReplayView(replay, source, interactive=not args.headless)
    if args.headless:
        try:
            headless_check(view, args.output)
        finally:
            plt.close(view.fig)
    else:
        plt.show()


if __name__ == "__main__":
    main()
