"""Chinese bounded RX monitor / checked archive replay. RF settings are read-only.

Without arguments, opens READY and waits for Start. --archive replays files;
--render-archive uses Agg and never opens a window or contacts hardware.
"""

import argparse
from collections import deque
from datetime import datetime, timezone
import json
from pathlib import Path
from queue import Empty, Full, Queue
import sys
from threading import Event, Thread
from time import perf_counter

import numpy as np

from rfsig.monitor_display import ArchiveReplay, save_display_snapshot
from rfsig.display_classifier import DisplayClassifier
from rfsig.rx_monitor import P201Receiver
from rfsig.stream_monitor import run_stream_monitor


ROOT = Path(__file__).resolve().parents[1]
DLL_DIR = Path(r"D:\FPGA natch\IIO-Oscilloscope-v0.18-portable\app\bin")


class StreamWindow:
    def __init__(self, dll_dir=DLL_DIR, uri="ip:192.168.2.1", *, archive=None, interactive=True,
                 output_root=None, receiver_factory=None, max_blocks=None,
                 source_kind="live_iio_rx_snapshots", model_path=None):
        import matplotlib.pyplot as plt
        from matplotlib import font_manager
        from matplotlib.widgets import Button
        try:
            font_manager.findfont("Microsoft YaHei", fallback_to_default=False)
            plt.rcParams["font.family"] = "Microsoft YaHei"
        except ValueError:
            plt.rcParams["font.family"] = "DejaVu Sans"
        plt.rcParams["axes.unicode_minus"] = False
        self.output_root = Path(output_root) if output_root else ROOT / "results"
        self.receiver_factory = receiver_factory or (lambda: P201Receiver(dll_dir, uri))
        self.max_blocks, self.interactive = max_blocks, interactive
        self.source_kind = source_kind
        self.classifier = DisplayClassifier(model_path) if model_path else None
        self.current_prediction = self.prediction_key = None
        self.replay = ArchiveReplay(archive) if archive is not None else None
        self.mode = "saved_archive" if self.replay else "live"
        self.queue, self.stop_event = Queue(maxsize=1), Event()
        self.worker, self.snapshot, self.archive_directory = None, None, None
        self.display_updates = self.display_replacements = 0
        self.presentation_times = deque(maxlen=120)
        self.last_presented_block = None
        self._background = None
        self._saving = False
        self._plot_layout = None
        self._amplitude_history = deque(maxlen=32)
        self._last_scale_block = None
        self.last_snapshot_time = None
        self._last_age_refresh = 0.
        self.fig = plt.figure(figsize=(13.8, 9.0))
        self.fig.canvas.manager.set_window_title("射频信号分析 · 持续快照监测 / 归档回放")
        grid = self.fig.add_gridspec(2, 2, left=.075, right=.92, bottom=.24, top=.85,
                                    wspace=.29, hspace=.51)
        self.time_ax, self.info_ax = self.fig.add_subplot(grid[0, 0]), self.fig.add_subplot(grid[0, 1])
        self.spec_ax, self.water_ax = self.fig.add_subplot(grid[1, 0]), self.fig.add_subplot(grid[1, 1])
        self.info_ax.axis("off")
        self.heading = self.fig.suptitle("已就绪 · 尚未连接采集", y=.975, fontsize=18, fontweight="bold")
        self.source_text = self.fig.text(.075, .916, "真实接收模式 · 目标未知 · AI 未接入", fontsize=11)
        self.age_text = self.fig.text(.075, .883, "点击开始后连接；沿用板卡已有射频配置。", fontsize=9)
        self.time_ax.set(xlabel="块内时间 (μs)", ylabel="I / Q 原始计数", title="I/Q 时域波形")
        self.spec_ax.set(xlabel="相对接收本振的频率偏移 (MHz)", ylabel="PSD (原始计数²/Hz，dB)", title="频谱 · 周期 Hann 窗")
        self.water_ax.set(xlabel="相对接收本振的频率偏移 (MHz)", ylabel="最近窗口内的行号（块间间隙未知）", title="瀑布图 · 最近 96 块")
        self.time_ax.grid(alpha=.25)
        self.spec_ax.grid(alpha=.25)
        self.i_line, = self.time_ax.plot([], [], lw=.7, label="I")
        self.q_line, = self.time_ax.plot([], [], lw=.7, label="Q")
        self.time_ax.legend(loc="upper right", fontsize=8)
        self.spectrum_line, = self.spec_ax.plot([], [], lw=.7)
        self.midpoint_line = self.spec_ax.axvline(0, color="red", ls="--", lw=.8, visible=False)
        self.band_patch = None
        self.image = self.water_ax.imshow(np.full((1, 2), -100.), aspect="auto", origin="lower",
                                         cmap="viridis", vmin=-100, vmax=0, extent=(-1, 1, .5, 1.5))
        self.image.set_visible(False)
        self.color_ax = self.fig.add_axes((.937, .24, .014, .243))
        self.fig.colorbar(self.image, cax=self.color_ax)
        self.color_ax.set_visible(False)
        self.info_text = self.info_ax.text(0, 1, "等待数据", va="top", fontsize=9, linespacing=1.25)
        self.empty_texts = [axis.text(.5, .5, "尚无接收数据", ha="center", va="center", transform=axis.transAxes)
                            for axis in (self.time_ax, self.spec_ax, self.water_ax)]
        self.fig.text(.075, .174,
                      "频谱区间含噪声：黄色区域为 ROI 内 99% 功率区间，红线为区间中点；尚未验证目标检测或真实 RF 参数精度。\n"
                      "原始数字功率不是 dBm；自动增益可能改变幅度。持续更新的是接收快照，硬件连续性与丢样仍未知。\n"
                      "实时模式：自动分段保存；内存保留最近 96 块，归档到 512 MiB 上限时正常停止。", fontsize=8.5, va="top")
        self.status = self.fig.text(.075, .026, "就绪。旧监测程序与新程序请勿同时启动采集。", fontsize=8.5)
        self.buttons = []
        labels = ((.12, "开始 / 新会话", self.start), (.34, "停止接收", self.stop),
                  (.56, "保存当前画面", self.save), (.78, "重置回放", self.reset_replay))
        for left, label, callback in labels:
            button = Button(self.fig.add_axes((left, .062, .16, .045)), label)
            button.on_clicked(callback)
            self.buttons.append(button)
        if self.replay:
            self.heading.set_text("已保存归档 · 暂停 · 非实时射频")
            provenance = "保存的真实接收" if self.replay.summary["source_kind"] == "live_iio_rx_snapshots" else "保存的模拟测试"
            ai_note = "电脑 CNN 合成演示（非板端实时识别）" if self.classifier else "AI 未接入"
            self.source_text.set_text(f"归档回放模式 · {provenance} · {ai_note}")
            self.age_text.set_text("回放速度与原始采样时间独立；不会连接板卡。")
            self.buttons[0].label.set_text("开始 / 继续回放")
            self.buttons[1].label.set_text("暂停回放")
            self.snapshot = self.replay.snapshot()
        else:
            self.buttons[3].set_active(False)
            self.buttons[3].label.set_alpha(.4)
        # Tk timers wait again after the callback returns. A 100 ms timer plus
        # rendering time unnecessarily throttled the former full-redraw viewer.
        self.timer = self.fig.canvas.new_timer(interval=25)
        self.timer.add_callback(self.poll)
        self.fig.canvas.mpl_connect("close_event", self.close)
        self.use_blit = bool(interactive and self.fig.canvas.supports_blit)
        self.fig.canvas.mpl_connect("draw_event", self._capture_background)
        self.fig.canvas.mpl_connect("resize_event", lambda _: self._invalidate_background())
        if self.use_blit:
            for artist in self._dynamic_artists():
                artist.set_animated(True)
        if interactive:
            self.timer.start()

    def _dynamic_artists(self):
        artists = [self.i_line, self.q_line, self.spectrum_line, self.midpoint_line,
                   self.image, self.info_text, self.heading, self.source_text,
                   self.age_text, self.status, self.water_ax.title, *self.empty_texts]
        if self.band_patch is not None:
            artists.insert(0, self.band_patch)
        return artists

    def _invalidate_background(self):
        self._background = None

    def _capture_background(self, event):
        if self.use_blit and not self._saving:
            self._background = self.fig.canvas.copy_from_bbox(self.fig.bbox)
            self._draw_dynamic()

    def _draw_dynamic(self):
        for artist in self._dynamic_artists():
            if artist.get_visible():
                self.fig.draw_artist(artist)

    def present(self):
        """Submit new artists to the canvas; this is not measured physical display FPS."""
        if self.use_blit and self._background is not None:
            self.fig.canvas.restore_region(self._background)
            self._draw_dynamic()
            self.fig.canvas.blit(self.fig.bbox)
        else:
            self.fig.canvas.draw_idle()

    def presentation_metrics(self):
        span = self.presentation_times[-1]-self.presentation_times[0] if len(self.presentation_times)>1 else 0
        return {"new_data_canvas_updates": len(self.presentation_times),
                "recent_host_canvas_updates_per_second": (len(self.presentation_times)-1)/span if span>0 else None,
                "scope": "host canvas submission; not physical screen FPS, ADC throughput or RF latency",
                "blitting_enabled": self.use_blit}

    def publish(self, item):
        try:
            self.queue.put_nowait((item, perf_counter()))
        except Full:
            try:
                self.queue.get_nowait()
                self.display_replacements += 1
            except Empty:
                pass
            self.queue.put_nowait((item, perf_counter()))

    def start(self, event=None):
        if self.replay:
            self.replay.start()
            return
        if self.worker is not None and self.worker.is_alive():
            return
        self.snapshot, self.last_snapshot_time = None, None
        self.current_prediction = self.prediction_key = None
        self.queue, self.stop_event = Queue(maxsize=1), Event()
        self.display_updates = self.display_replacements = 0
        self.presentation_times.clear()
        self.last_presented_block = None
        self.clear_data()
        self.heading.set_text("正在连接 P201")
        self.status.set_text("连接并检查设备身份、格式和测试模式；沿用现有 RF 配置。")
        target = self.output_root / datetime.now(timezone.utc).strftime("p11-live-%Y%m%dT%H%M%S%fZ")
        self.archive_directory = target / "session"
        def receive():
            try:
                run_stream_monitor(self.receiver_factory, self.archive_directory,
                                   stop_event=self.stop_event, on_snapshot=self.publish,
                                   max_blocks=self.max_blocks, source_kind=self.source_kind)
            except Exception as error:
                self.publish({"worker_error": f"{type(error).__name__}: {error}"})
        self.worker = Thread(target=receive, name="p201-stream-monitor", daemon=False)
        self.worker.start()
        self.present()

    def stop(self, event=None):
        if self.replay:
            self.replay.pause()
            self.snapshot = self.replay.snapshot()
            self.draw_snapshot()
        elif self.worker is not None and self.worker.is_alive():
            self.stop_event.set()
            self.heading.set_text("正在停止 · 等待接收释放与末段保存")
            self.present()

    def reset_replay(self, event=None):
        if self.replay:
            self.replay.reset()
            self.snapshot = self.replay.snapshot()
            self.clear_data()
            self.heading.set_text("已保存归档 · 已重置 · 非实时射频")
            self.info_text.set_text("回放位置 0 / " + str(self.replay.total))
            self.status.set_text("已清空回放位置和图形；点击开始重新回放，原始归档保留。")
            self.present()
        else:
            self.status.set_text("实时模式请先停止，再开始新会话；已有归档会保留。")
            self.present()

    def clear_data(self):
        self._invalidate_background()
        self._plot_layout = None
        self._amplitude_history.clear()
        self._last_scale_block = None
        self.current_prediction = self.prediction_key = None
        for line in (self.i_line, self.q_line, self.spectrum_line):
            line.set_data([], [])
        self.midpoint_line.set_visible(False)
        self.image.set_visible(False)
        self.color_ax.set_visible(False)
        if self.band_patch is not None:
            self.band_patch.remove()
            self.band_patch = None
        for label in self.empty_texts:
            label.set_visible(True)
        self.info_text.set_text("等待数据")

    def poll(self):
        if self.replay:
            if self.replay.state == "playing":
                self.snapshot = self.replay.advance()
                self.display_updates += 1
                self.draw_snapshot()
            return
        try:
            item, published = self.queue.get_nowait()
        except Empty:
            if (self.last_snapshot_time is not None and self.worker is not None and self.worker.is_alive()
                    and perf_counter()-self._last_age_refresh >= .5):
                self._last_age_refresh = perf_counter()
                self.age_text.set_text(f"最近画面快照已过去 {perf_counter()-self.last_snapshot_time:.1f} s（主机时间，不是射频延迟）")
                self.present()
            return
        if isinstance(item, dict) and "worker_error" in item:
            self.heading.set_text("连接或采集失败 · 请查看日志")
            self.status.set_text(item["worker_error"])
            print(item["worker_error"], file=sys.stderr, flush=True)
            self.present()
            return
        self.snapshot, self.last_snapshot_time = item, published
        self.display_updates += 1
        self.draw_snapshot()

    def draw_snapshot(self):
        if self.snapshot is None:
            return
        report, arrays = self.snapshot
        count = report["retained_block_count"]
        state = report.get("playback_state", report["state"])
        if self.replay:
            playback_name = {"playing": "正在回放", "paused": "已暂停", "finished": "回放结束"}.get(state, state)
            self.heading.set_text(f"已保存归档 · {playback_name} · 非实时射频")
            self.status.set_text(f"回放 {report['playback_position']}/{report['playback_total_blocks']} 块；原始采集状态 {report['state']}。")
        else:
            names = {"running": "接收中", "stopped": "已停止", "time_limit": "到达时长上限",
                     "block_limit": "到达块数上限", "archive_limit": "到达归档容量上限",
                     "error": "发生错误", "interrupted": "已中断"}
            origin = "模拟测试数据 · 非真实射频" if report["source_kind"] == "synthetic_test" else "真实接收快照 · 目标未知"
            self.heading.set_text(names.get(state, state) + " · " + origin)
            if self.stop_event.is_set() and state == "running":
                self.heading.set_text("正在停止 · 等待接收释放与末段保存")
            self.status.set_text(report["error"] or f"自动归档：{Path(report['archive_directory']).parent.name}；保存按钮另导出最近窗口。")
            if report["source_kind"] == "synthetic_test":
                self.source_text.set_text("模拟测试数据 · 不是实际射频 · AI 未接入")
            else:
                self.source_text.set_text("真实接收快照 · 数据来自 IIO · 目标未知 · AI 未接入")
            self.age_text.set_text("采集中" if state == "running" else "本次接收已结束；图形保留最终快照。")
        if not count:
            self.clear_data()
            self.present()
            return
        for label in self.empty_texts:
            label.set_visible(False)
        fs, n = report["settings"]["sample_rate_hz"], report["fft_size"]
        synthetic = report["source_kind"] == "synthetic_test"
        layout = (fs, n, synthetic, report["history_capacity"])
        if layout != self._plot_layout:
            self.time_ax.set_ylabel("I / Q 归一化幅度" if synthetic else "I / Q 原始计数")
            self.spec_ax.set_ylabel("PSD (归一化幅度²/Hz，dB)" if synthetic else "PSD (原始计数²/Hz，dB)")
            self._plot_layout = layout
            self._invalidate_background()
        time_us = np.arange(n) / fs * 1e6
        self.i_line.set_data(time_us, arrays["iq_frames"][-1].real)
        self.q_line.set_data(time_us, arrays["iq_frames"][-1].imag)
        freq = arrays["frequency_hz"] / 1e6
        self.spectrum_line.set_data(freq, 10*np.log10(np.maximum(arrays["psd_frames"][-1], 1e-16)))
        if self._background is None:
            self.time_ax.set_xlim(time_us[0], time_us[-1])
            self.spec_ax.set_xlim(freq[0], freq[-1])
        # Keep ticks stable between frames. Expand only when data escapes the
        # current range; repeated full tick/layout rendering otherwise dominates RX.
        amplitude = max(float(np.max(np.abs(arrays["iq_frames"][-1].real))),
                        float(np.max(np.abs(arrays["iq_frames"][-1].imag))), 1e-9)
        scale_block = int(arrays["block_numbers"][-1])
        if scale_block != self._last_scale_block:
            self._amplitude_history.append(amplitude)
            self._last_scale_block = scale_block
        recent_amplitude = max(self._amplitude_history)
        limit = 2.0 ** np.ceil(np.log2(recent_amplitude*1.2))
        old_low, old_high = self.time_ax.get_ylim()
        if self._background is None or limit > old_high or limit <= old_high/2:
            self.time_ax.set_ylim(-limit, limit)
            self._invalidate_background()
        spectrum_db = self.spectrum_line.get_ydata()
        low = float(np.floor(np.min(spectrum_db)/20)*20-10)
        high = float(np.ceil(np.max(spectrum_db)/20)*20+10)
        old_low, old_high = self.spec_ax.get_ylim()
        if self._background is None or low < old_low or high > old_high:
            self.spec_ax.set_ylim(min(low, old_low) if self._background is not None else low,
                                  max(high, old_high) if self._background is not None else high)
            self._invalidate_background()
        band = report["bandwidths"][-1]
        if self.band_patch is not None:
            self.band_patch.remove()
            self.band_patch = None
        if band["status"] == "ok":
            self.band_patch = self.spec_ax.axvspan(band["lower_hz"]/1e6, band["upper_hz"]/1e6, color="orange", alpha=.2)
            self.band_patch.set_animated(self.use_blit)
            self.midpoint_line.set_xdata([band["center_baseband_hz"]/1e6]*2)
            self.midpoint_line.set_visible(True)
        else:
            self.midpoint_line.set_visible(False)
        self.image.set_data(10*np.log10(np.maximum(arrays["psd_frames"], 1e-16)))
        df = fs / n / 1e6
        self.image.set_extent((freq[0]-df/2, freq[-1]+df/2,
                               .5, count+.5))
        # Fixed rolling-window coordinates permit cached axes/ticks. Absolute
        # block numbers remain in the adjacent information and saved arrays.
        self.water_ax.set_ylim(.5, report["history_capacity"]+.5)
        self.image.set_visible(True)
        self.color_ax.set_visible(True)
        self.water_ax.set_title(f"瀑布图 · 最近 {count} 块（块间间隙未知）")
        relative = report["relative_db"][-1]
        ratio = f"{relative:+.3f} dB" if relative is not None else report["relative_db_status"][-1]
        interval = f"{band['bandwidth_hz']/1e6:.5f} MHz" if band["status"] == "ok" else "无有效功率"
        midpoint = f"{band['center_baseband_hz']/1e6:+.5f} MHz" if band["status"] == "ok" else "N/A"
        settings = report["settings"]
        ai_text = "AI：未接入"
        if self.classifier:
            key = (int(arrays["block_numbers"][-1]), report["source_kind"], fs)
            if key != self.prediction_key:
                self.current_prediction = self.classifier.predict(
                    arrays["iq_frames"][-1], sample_rate_hz=fs,
                    source_kind=report["source_kind"], block_number=key[0])
                self.prediction_key = key
            result = self.current_prediction
            if result["status"] == "synthetic_replay_prediction":
                score = max(result["softmax_scores"])
                ai_text = (f"电脑 CNN（合成演示）：{result['class_name']}　对应块 {result['block_number']}\n"
                           f"最大 softmax 得分：{score:.3f}（未经正确率校准）\n"
                           "模型：CNN-115-v1 FP32；真实 RF 分类尚未验收")
            else:
                ai_text = "AI 暂不输出类别：" + result["status"]
        lo_text = "射频本振：不适用（合成基带）" if synthetic else f"接收本振：{settings['rx_lo_hz']/1e6:g} MHz"
        gain_text = "接收增益：不适用（合成数据）" if synthetic else f"增益：{settings['gain_control_mode']} / {arrays['gain_after_db'][-1]:g} dB"
        self.info_text.set_text(
            f"累计接收：{report['received_block_count']} 块　显示缓存：{count}/{report['history_capacity']}\n"
            f"窗口块号：{int(arrays['block_numbers'][0])}–{int(arrays['block_numbers'][-1])}\n"
            f"归档：{report['archived_block_count']} 块 / {report['archive_chunk_count']} 段\n"
            f"采样率：{fs/1e6:g} MS/s　FFT：{n} 点\n"
            f"{lo_text}\n"
            f"接收滤波带宽：{settings['rx_rf_bandwidth_hz']/1e6:g} MHz\n"
            f"{gain_text}\n"
            f"当前平均数字功率：{arrays['mean_power'][-1]:.6g}\n"
            f"相对本会话参考：{ratio}\n"
            f"99% ROI 区间宽度：{interval}\n"
            f"ROI 区间中点：{midpoint}\n"
            f"画面更新／队列替换：{self.display_updates} / {self.display_replacements}\n"
            f"{ai_text}\n"
            f"硬件丢样：{'不适用（文件）' if synthetic else '未知'}\n"
            f"接收资源已释放：{report['receive_context_released']}\n"
            f"归档完整收尾：{report['archive_finalized']}")
        self.present()
        block = int(arrays["block_numbers"][-1])
        if block != self.last_presented_block:
            self.presentation_times.append(perf_counter())
            self.last_presented_block = block

    def save(self, event=None):
        try:
            if self.snapshot is None or not self.snapshot[0]["retained_block_count"]:
                raise ValueError("暂无数据，请先采集或回放。")
            target = self.output_root / datetime.now(timezone.utc).strftime("p11-display-%Y%m%dT%H%M%S%fZ")
            report, arrays = self.snapshot
            exported_snapshot = ({**report, "display_ai_prediction": self.current_prediction,
                                  "display_presentation": self.presentation_metrics()}, arrays)
            save_display_snapshot(exported_snapshot, target, display_mode=self.mode,
                                  display_updates=self.display_updates,
                                  display_replacements=self.display_replacements)
            self._saving = True
            artists = self._dynamic_artists()
            try:
                for artist in artists:
                    artist.set_animated(False)
                self.fig.savefig(target / "viewer.png", dpi=120)
            finally:
                for artist in artists:
                    artist.set_animated(self.use_blit)
                self._saving = False
                self._invalidate_background()
            self.status.set_text("已保存当前窗口：" + target.name + "；全部原始块另见自动归档。")
            print("Saved display:", target, flush=True)
            return target
        except Exception as error:
            self.status.set_text(f"保存失败：{type(error).__name__}: {error}")
            print(f"Save failed: {error}", file=sys.stderr, flush=True)
            return None
        finally:
            self.present()

    def close(self, event=None):
        self.timer.stop()
        self.stop_event.set()
        if self.worker is not None:
            self.worker.join(timeout=5)
            if self.worker.is_alive():
                print("Waiting for RX cleanup and final archive flush.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--libiio-dir", type=Path, default=DLL_DIR)
    parser.add_argument("--uri", default="ip:192.168.2.1")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--archive", type=Path)
    group.add_argument("--render-archive", type=Path)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--model", type=Path, help="Frozen synthetic CNN; only for explicitly selected archive replay")
    args = parser.parse_args()
    if args.model and not (args.archive or args.render_archive):
        parser.error("--model requires --archive or --render-archive; real RX inference is not validated")
    import matplotlib
    matplotlib.use("Agg" if args.render_archive else "TkAgg")
    import matplotlib.pyplot as plt
    archive = args.render_archive or args.archive
    window = StreamWindow(args.libiio_dir, args.uri, archive=archive,
                          interactive=not args.render_archive, output_root=args.output_root, model_path=args.model)
    if args.render_archive:
        window.replay.start()
        while window.replay.state == "playing":
            window.snapshot = window.replay.advance()
        window.draw_snapshot()
        target = window.save()
        plt.close(window.fig)
        if target is None:
            raise RuntimeError("Archive render/export failed")
    else:
        print("Ready. Start opens RX; automatic chunk archive, no RF/TX writes.", flush=True)
        plt.show()


if __name__ == "__main__":
    main()
