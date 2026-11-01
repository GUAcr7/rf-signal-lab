"""User-operated finite live RX monitor; --render-record uses Agg and no hardware.

RX occurs on one worker thread. Only the GUI thread touches Matplotlib. All
blocks remain in a bounded session; the display queue only keeps the latest.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from queue import Empty, Full, Queue
import sys
from threading import Event, Thread

import numpy as np

from rfsig.rx_monitor import P201Receiver, run_monitor_session, save_monitor_snapshot


ROOT = Path(__file__).resolve().parents[1]
DLL_DIR = Path(r"D:\FPGA natch\IIO-Oscilloscope-v0.18-portable\app\bin")


class MonitorWindow:
    def __init__(self, dll_dir, uri, interactive=True):
        import matplotlib.pyplot as plt
        from matplotlib.widgets import Button

        self.dll_dir, self.uri, self.interactive = dll_dir, uri, interactive
        self.queue, self.stop_event = Queue(maxsize=1), Event()
        self.worker, self.snapshot = None, None
        self.queue_replacements, self.draw_updates = 0, 0
        self.fig = plt.figure(figsize=(12.8, 8.6))
        self.fig.canvas.manager.set_window_title("RF signal analysis - IIO RX MONITOR")
        grid = self.fig.add_gridspec(2, 2, left=0.075, right=0.925, bottom=0.235, top=0.87,
                                    wspace=0.28, hspace=0.45)
        self.time_ax, self.info_ax = self.fig.add_subplot(grid[0, 0]), self.fig.add_subplot(grid[0, 1])
        self.spec_ax, self.water_ax = self.fig.add_subplot(grid[1, 0]), self.fig.add_subplot(grid[1, 1])
        self.color_ax = self.fig.add_axes((0.939, 0.235, 0.013, 0.259))
        self.heading = self.fig.suptitle("READY | RX NOT STARTED", y=0.97, fontsize=15, fontweight="bold")
        self.fig.text(0.075, 0.91, "IIO receive monitoring. Target unknown. AI: NOT CONNECTED.", fontsize=10)
        self.fig.text(0.075, 0.153,
                      "Each row is one received block. Gaps / receive latency are unverified; no continuous ADC-time axis.\n"
                      "Digital power and 99% ROI interval include unknown input/noise. AGC is active unless stated otherwise.\n"
                      "Start opens a new session and reference. Stop waits for in-flight I/O and releases RX. No RF/TX writes.",
                      fontsize=9, va="top")
        self.status = self.fig.text(0.075, 0.019, "Ready. Click Start to connect and receive up to 120 blocks.", fontsize=9)
        self.buttons = []
        for left, label, callback in ((0.17, "Start / New session", self.start),
                                      (0.43, "Stop RX", self.stop), (0.69, "Save", self.save)):
            axis = self.fig.add_axes((left, 0.055, 0.17, 0.045))
            button = Button(axis, label)
            button.on_clicked(callback)
            self.buttons.append(button)
        self.timer = self.fig.canvas.new_timer(interval=100)
        self.timer.add_callback(self.poll)
        self.fig.canvas.mpl_connect("close_event", self.close)
        self.draw()
        if interactive:
            self.timer.start()

    def publish(self, message):
        try:
            self.queue.put_nowait(message)
        except Full:
            try:
                self.queue.get_nowait()
                self.queue_replacements += 1
            except Empty:
                pass
            self.queue.put_nowait(message)

    def start(self, event=None):
        if not self.interactive or (self.worker is not None and self.worker.is_alive()):
            return
        self.snapshot = None
        self.queue = Queue(maxsize=1)
        self.queue_replacements = self.draw_updates = 0
        self.stop_event = Event()
        self.heading.set_text("CONNECTING TO P201")
        self.status.set_text("Connecting; retaining existing RF settings. No transmit operation.")
        self.draw()
        def receive():
            try:
                run_monitor_session(lambda: P201Receiver(self.dll_dir, self.uri), frame_limit=120,
                                    interval_seconds=0.1, stop_event=self.stop_event,
                                    on_snapshot=lambda snapshot: self.publish((snapshot, None)))
            except Exception as error:
                notes = "; ".join(getattr(error, "__notes__", []))
                self.publish((None, f"{type(error).__name__}: {error}"+(f"; {notes}" if notes else "")))
        self.worker = Thread(target=receive, name="p201-rx-monitor", daemon=False)
        self.worker.start()

    def stop(self, event=None):
        if self.worker is not None and self.worker.is_alive():
            self.stop_event.set()
            self.heading.set_text("STOPPING RX")
            self.status.set_text("Stop requested. Waiting for in-flight read and RX context release.")
            self.fig.canvas.draw_idle()

    def poll(self):
        try:
            snapshot, error = self.queue.get_nowait()
        except Empty:
            return  # None retains the timer callback.
        if error is not None:
            self.heading.set_text("RX ERROR | CHECK LOG")
            if self.snapshot is not None:
                report, arrays = self.snapshot
                self.snapshot = ({**report, "state": "error", "error": error,
                                  "receive_context_released": False,
                                  "receive_context_release_note": "Unknown after worker exception; inspect log."}, arrays)
            self.status.set_text(error)
            print(error, file=sys.stderr, flush=True)
            self.draw()
            return
        self.snapshot = snapshot
        self.draw_updates += 1
        report = snapshot[0]
        if self.stop_event.is_set() and report["state"] == "running":
            self.heading.set_text("STOPPING RX")
        elif report["state"] == "running":
            self.heading.set_text("LIVE IIO RX | TARGET UNKNOWN")
        else:
            self.heading.set_text("RX STOPPED | RECEIVED SNAPSHOTS")
        if report["error"]:
            self.status.set_text(report["error"])
        elif self.stop_event.is_set() and report["state"] == "running":
            self.status.set_text("Stop requested. Waiting for in-flight read and RX context release.")
        elif report["state"] != "running":
            self.status.set_text("RX released. Save before starting a new session. Start clears the old session.")
        else:
            self.status.set_text("Receiving new blocks; display may skip updates. All acquired session blocks are retained.")
        self.draw()

    def draw(self):
        for axis in (self.time_ax, self.spec_ax, self.water_ax, self.info_ax, self.color_ax):
            axis.clear()
        self.info_ax.axis("off")
        self.color_ax.set_visible(False)
        self.time_ax.set(xlabel="Time within RX block (us)", ylabel="I / Q (raw counts)", title="I/Q time domain")
        self.spec_ax.set(xlabel="Baseband frequency offset (MHz)", ylabel="PSD (raw count^2/Hz, dB)",
                         title="Spectrum | Hann window")
        self.water_ax.set(xlabel="Baseband frequency offset (MHz)", ylabel="Received block number (gaps unknown)",
                          title="Waterfall | received snapshots")
        self.time_ax.grid(alpha=0.25)
        self.spec_ax.grid(alpha=0.25)
        if self.snapshot is None or not self.snapshot[0]["frame_count"]:
            for axis in (self.time_ax, self.spec_ax, self.water_ax):
                axis.text(0.5, 0.5, "No RX data", transform=axis.transAxes, ha="center")
        else:
            report, arrays = self.snapshot
            count, n = report["frame_count"], report["fft_size"]
            fs = report["settings"]["sample_rate_hz"]
            iq, freq, psd = arrays["iq_frames"][-1], arrays["frequency_hz"], arrays["psd_frames"][-1]
            t = np.arange(n)/fs*1e6
            self.time_ax.plot(t, iq.real, lw=0.7, label="I")
            self.time_ax.plot(t, iq.imag, lw=0.7, label="Q")
            self.time_ax.legend(loc="upper right", fontsize=8)
            self.spec_ax.plot(freq/1e6, 10*np.log10(np.maximum(psd, 1e-16)), lw=0.7)
            band = report["bandwidths"][-1]
            if band["status"] == "ok":
                self.spec_ax.axvspan(band["lower_hz"]/1e6, band["upper_hz"]/1e6, alpha=0.2, color="orange")
                self.spec_ax.axvline(band["center_baseband_hz"]/1e6, ls="--", color="red", lw=1)
            rows = min(96, count)
            df = fs/n
            mesh = self.water_ax.imshow(10*np.log10(np.maximum(arrays["psd_frames"][-rows:], 1e-16)),
                                        origin="lower", aspect="auto", cmap="viridis", vmin=-100, vmax=0,
                                        extent=((freq[0]-df/2)/1e6, (freq[-1]+df/2)/1e6,
                                                count-rows+0.5, count+0.5))
            self.color_ax.set_visible(True)
            self.fig.colorbar(mesh, cax=self.color_ax).ax.tick_params(labelsize=8)
            self.water_ax.set_title(f"Waterfall | last {rows} of {count} received blocks", fontsize=10)
            relative = report["relative_db"][-1]
            ratio = f"{relative:+.3f} dB" if relative is not None else report["relative_db_status"][-1]
            gain = arrays["gain_after_db"][-1]
            width = f"{band['bandwidth_hz']/1e6:.5g} MHz" if band["status"] == "ok" else "N/A"
            center = f"{band['center_baseband_hz']/1e6:.5g} MHz" if band["status"] == "ok" else "N/A"
            state = "STOPPING" if self.stop_event.is_set() and report["state"] == "running" else report["state"].upper()
            info = (f"State: {state}\nReceived blocks: {count}/{report['frame_limit']}\n"
                    f"Fs: {fs/1e6:g} MS/s   FFT: {n}\nRX LO: {report['settings']['rx_lo_hz']/1e6:g} MHz\n"
                    f"RF BW: {report['settings']['rx_rf_bandwidth_hz']/1e6:g} MHz\n"
                    f"Gain: {report['settings']['gain_control_mode']}  {gain:g} dB\n"
                    f"Host elapsed: {report['host_elapsed_to_last_rx_seconds']:.3f} s\n"
                    f"Observed blocks/s: {report['observed_blocks_per_host_second']:.2f}\n"
                    f"Mean I^2+Q^2: {arrays['mean_power'][-1]:.6g}\nDigital ratio: {ratio}\n"
                    f"99% ROI width: {width}\nROI midpoint: {center}\n"
                    f"Hardware gaps: UNKNOWN\nRX context released: {report['receive_context_released']}")
            self.info_ax.text(0, 1, info, va="top", fontsize=9, family="monospace", linespacing=1.25)
        self.fig.canvas.draw_idle()

    def save(self, event=None):
        try:
            if self.snapshot is None:
                raise ValueError("No received snapshot to save")
            report, arrays = self.snapshot
            report = {**report, "display_queue_replacements": self.queue_replacements,
                      "gui_draw_updates": self.draw_updates,
                      "display_note": "Queue replacement counts are not ADC dropped samples; last 96 acquired rows shown."}
            target = ROOT/"results"/datetime.now(timezone.utc).strftime("p05-rx-monitor-gui-%Y%m%dT%H%M%S%fZ")
            save_monitor_snapshot((report, arrays), target)
            self.status.set_text(f"Saved: {target.name} (PNG + NPZ + JSON)")
            self.fig.savefig(target/"viewer.png", dpi=120)
            print(f"Saved evidence: {target}", flush=True)
        except Exception as error:
            self.status.set_text(f"Save failed: {error}")
            print(f"Save failed: {error}", file=sys.stderr, flush=True)
        self.fig.canvas.draw_idle()

    def close(self, event=None):
        self.timer.stop()
        self.stop_event.set()
        if self.worker is not None:
            self.worker.join(timeout=5)
            if self.worker.is_alive():
                print("Waiting for in-flight IIO cleanup; process exits after worker finishes.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--libiio-dir", type=Path, default=DLL_DIR)
    parser.add_argument("--uri", default="ip:192.168.2.1")
    parser.add_argument("--render-record", type=Path, help="Render a saved finite monitor session without IIO or GUI")
    args = parser.parse_args()
    import matplotlib
    matplotlib.use("Agg" if args.render_record else "TkAgg")
    import matplotlib.pyplot as plt
    window = MonitorWindow(args.libiio_dir, args.uri, interactive=not bool(args.render_record))
    if args.render_record:
        try:
            path = args.render_record
            report = json.loads((path/"report.json").read_text(encoding="utf-8"))
            if hashlib.sha256((path/"monitor.npz").read_bytes()).hexdigest() != report["arrays_sha256"]:
                raise ValueError("Saved monitor arrays hash mismatch")
            with np.load(path/"monitor.npz", allow_pickle=False) as saved:
                window.snapshot = report, {key: saved[key].copy() for key in saved.files}
            window.heading.set_text("SAVED MONITOR CHECK | NOT LIVE")
            window.status.set_text("Headless rendering from saved data; no hardware connection or GUI events.")
            window.draw()
            target = ROOT/"results"/datetime.now(timezone.utc).strftime("p05-rx-monitor-render-%Y%m%dT%H%M%S%fZ")
            target.mkdir()
            window.fig.savefig(target/"viewer.png", dpi=120)
            verification = {"source": str(path.resolve()), "source_arrays_sha256": report["arrays_sha256"],
                            "blocks_rendered": report["frame_count"], "gui_verified": False,
                            "hardware_contacted_by_renderer": False,
                            "source_code_sha256": {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
                                                   for name in ("host/rx_monitor_viewer.py", "src/rfsig/rx_monitor.py")},
                            "viewer_png_sha256": hashlib.sha256((target/"viewer.png").read_bytes()).hexdigest()}
            (target/"verification.json").write_text(json.dumps(verification, indent=2)+"\n", encoding="utf-8")
            print("Headless render:", target, flush=True)
        finally:
            plt.close(window.fig)
    else:
        print("Ready. User clicks Start to open one P201 RX session. No TX or retune.", flush=True)
        plt.show()


if __name__ == "__main__":
    main()
