"""Agg tests exercise controller callbacks, not claimed physical GUI clicks."""

from pathlib import Path
from time import perf_counter

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from host.stream_monitor_viewer import StreamWindow
from rfsig.rx_monitor import RxBlock
from rfsig.stream_monitor import verify_stream_archive


class SyntheticReceiver:
    fft_size = 64
    settings = {"sample_rate_hz": 64000, "rx_rf_bandwidth_hz": 48000,
                "rx_lo_hz": 2400000000, "gain_control_mode": "slow_attack", "rx_port": "A_BALANCED"}
    def __init__(self):
        self.index, self.cleanup_completed = 0, False
    def __enter__(self):
        return self
    def read(self):
        start = perf_counter()
        iq = (self.index+1)*np.exp(2j*np.pi*5*np.arange(self.fft_size)/self.fft_size)
        self.index += 1
        return RxBlock(iq, start, perf_counter(), 10., 11.)
    def __exit__(self, *_):
        self.cleanup_completed = True


def new_window(tmp_path, **kwargs):
    return StreamWindow(interactive=False, output_root=tmp_path, receiver_factory=SyntheticReceiver,
                        max_blocks=4, source_kind="synthetic_test", **kwargs)


def finish_worker(window):
    window.worker.join(timeout=10)
    assert not window.worker.is_alive()
    window.poll()


def test_live_controller_archive_export_and_new_session(tmp_path):
    window = new_window(tmp_path)
    try:
        assert window.save() is None
        window.start()
        finish_worker(window)
        first = window.archive_directory
        assert verify_stream_archive(first)["verified_blocks"] == 4
        assert window.snapshot[0]["source_kind"] == "synthetic_test"
        assert "模拟测试" in window.source_text.get_text()
        assert len(window.time_ax.lines) == 2 and len(window.spec_ax.lines) == 2
        assert len(window.fig.axes) == 9  # four plots, one colorbar, four controls
        for _ in range(4):
            window.draw_snapshot()
        assert len(window.fig.axes) == 9 and len(window.spec_ax.patches) == 1
        exported = window.save()
        assert exported is not None and (exported / "viewer.png").exists()
        window.start()
        finish_worker(window)
        assert window.archive_directory != first
        assert window.snapshot[0]["received_block_count"] == 4
        assert verify_stream_archive(first)["archive_complete"]
    finally:
        window.close()
        plt.close(window.fig)


def test_replay_controls_never_invoke_receiver_and_reset_clears_all_graphs(tmp_path):
    live = new_window(tmp_path)
    live.start()
    finish_worker(live)
    archive = live.archive_directory
    live.close()
    plt.close(live.fig)
    def forbidden():
        raise AssertionError("Archive replay must not connect to hardware")
    replay = StreamWindow(interactive=False, output_root=tmp_path, archive=archive, receiver_factory=forbidden)
    try:
        replay.start()
        replay.poll()
        assert replay.replay.position == 1
        replay.stop()
        replay.poll()
        assert replay.replay.position == 1
        replay.start()
        for _ in range(5):
            replay.poll()
        assert replay.replay.state == "finished"
        assert "非实时" in replay.heading.get_text()
        replay.reset_replay()
        assert replay.replay.position == 0
        assert not replay.image.get_visible()
        assert len(replay.i_line.get_xdata()) == 0
        assert replay.band_patch is None
        assert replay.save() is None
    finally:
        replay.close()
        plt.close(replay.fig)


def test_controller_connection_error_has_clear_state_and_no_old_data(tmp_path):
    def fail():
        raise OSError("deliberate offline test")
    window = StreamWindow(interactive=False, output_root=tmp_path, receiver_factory=fail)
    try:
        window.start()
        finish_worker(window)
        assert "失败" in window.heading.get_text()
        assert "deliberate offline test" in window.status.get_text()
        assert window.snapshot is None
        assert not window.archive_directory.exists()
    finally:
        window.close()
        plt.close(window.fig)


def test_model_overlay_and_export_refer_to_same_saved_frame(tmp_path, monkeypatch):
    import hashlib
    import json
    import host.stream_monitor_viewer as viewer
    from rfsig.display_classifier import DisplayClassifier
    from rfsig.trainable_cnn import initialize
    model = tmp_path / "test-model.npz"
    np.savez(model, **initialize())
    digest = hashlib.sha256(model.read_bytes()).hexdigest()
    monkeypatch.setattr(viewer, "DisplayClassifier", lambda path: DisplayClassifier(path, digest))
    class AtTrainingRate(SyntheticReceiver):
        fft_size = 1024
        settings = {**SyntheticReceiver.settings, "sample_rate_hz": 1000000, "rx_rf_bandwidth_hz": 800000}
    live = StreamWindow(interactive=False, output_root=tmp_path, receiver_factory=AtTrainingRate,
                        max_blocks=4, source_kind="synthetic_test")
    live.start()
    finish_worker(live)
    archive = live.archive_directory
    live.close()
    plt.close(live.fig)
    replay = StreamWindow(interactive=False, output_root=tmp_path, archive=archive, model_path=model)
    try:
        replay.start()
        replay.poll()
        replay.poll()
        assert replay.current_prediction["block_number"] == 2
        assert replay.current_prediction["status"] == "synthetic_replay_prediction"
        assert "合成演示" in replay.info_text.get_text()
        target = replay.save()
        report = json.loads((target / "snapshot.json").read_text(encoding="utf-8"))
        assert report["display_ai_prediction"]["block_number"] == report["history_last_block_number"] == 2
        assert report["display_ai_prediction"]["inference_location"] == "host_PC"
        assert not report["display_ai_prediction"]["real_rf_accuracy_verified"]
    finally:
        replay.close()
        plt.close(replay.fig)


def test_blitted_canvas_and_png_export_keep_data_and_reset_clears_it(tmp_path):
    import json
    from PIL import Image
    window = StreamWindow(interactive=True, output_root=tmp_path, receiver_factory=SyntheticReceiver,
                          max_blocks=4, source_kind="synthetic_test")
    try:
        assert window.use_blit
        window.fig.canvas.draw()
        assert window._background is not None
        window.start()
        finish_worker(window)
        assert window._background is not None
        before = np.asarray(window.fig.canvas.buffer_rgba()).copy()
        window.draw_snapshot()
        np.testing.assert_array_equal(before, np.asarray(window.fig.canvas.buffer_rgba()))
        target = window.save()
        report = json.loads((target/'snapshot.json').read_text(encoding='utf-8'))
        assert report['display_presentation']['blitting_enabled']
        assert report['display_presentation']['new_data_canvas_updates'] == 1
        pixels = np.asarray(Image.open(target/'viewer.png').convert('RGB'))
        # Yellow/green/blue data must remain in the waterfall after temporarily
        # disabling animation for savefig. A blank white axes would fail this.
        x0,x1,y0,y1 = window.image.get_extent()
        corners = window.water_ax.transData.transform([(x0,y0),(x1,y1)])
        corners = corners/np.array([window.fig.bbox.width,window.fig.bbox.height])
        left,right = (corners[:,0]*pixels.shape[1]).astype(int)
        top,bottom = ((1-corners[::-1,1])*pixels.shape[0]).astype(int)
        region = pixels[top+2:bottom-2,left+2:right-2]
        assert np.mean(np.max(region,axis=2)-np.min(region,axis=2)>40) > .5
        assert all(a.get_animated() for a in window._dynamic_artists())
        window.clear_data()
        window.present()
        assert window._background is not None
        assert not window.image.get_visible()
        assert len(window.i_line.get_xdata()) == 0
    finally:
        window.close()
        plt.close(window.fig)


def test_waveform_range_recovers_after_large_startup_transient(tmp_path):
    window = new_window(tmp_path)
    try:
        window.start()
        finish_worker(window)
        report,arrays=window.snapshot
        ordinary=arrays['iq_frames'][-1].copy()
        arrays['iq_frames'][-1]=ordinary*100
        arrays['block_numbers'][-1]=5
        window.draw_snapshot()
        large_limit=window.time_ax.get_ylim()[1]
        arrays['iq_frames'][-1]=ordinary
        # Duplicate presentation must not advance the transient's lifetime.
        for _ in range(35): window.draw_snapshot()
        assert window.time_ax.get_ylim()[1]==large_limit
        for block in range(6,40):
            arrays['block_numbers'][-1]=block
            window.draw_snapshot()
        recovered=window.time_ax.get_ylim()[1]
        assert recovered < large_limit/4
        assert recovered > np.max(np.abs(ordinary.real))
    finally:
        window.close()
        plt.close(window.fig)
