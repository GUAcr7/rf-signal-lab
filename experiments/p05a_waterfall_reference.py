"""Offline waterfall/replay validation: synthetic switches and one saved RX frame."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
from time import perf_counter

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from rfsig.iq_recording import load_iq_record
from rfsig.waterfall import WaterfallHistory, waterfall_periodogram


ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def plot_waterfall(axis, frequency, time, psd, frequency_scale, time_scale,
                   xlabel, ylabel, title, db_low, db_high):
    # Log clipping is visualization only; persisted PSD remains linear.
    db = 10*np.log10(np.maximum(psd, 1e-16))
    mesh = axis.pcolormesh(frequency/frequency_scale, time*time_scale, db,
                          shading="nearest", cmap="viridis", vmin=db_low, vmax=db_high)
    axis.set(xlabel=xlabel, ylabel=ylabel, title=title)
    return mesh


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--record", type=Path, default=ROOT/"results"/"p02-20261003T100526764044Z")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    # Independent ground truth: 32 ms per constant-frequency region.
    fs, fft_size, hop = 1_024_000, 1024, 512
    region_samples = 32768
    region_frequency = np.array([-128_000., 128_000., 256_000.])
    frequency_per_sample = np.repeat(region_frequency, region_samples)
    phase = 2*np.pi*np.concatenate(([0.], np.cumsum(frequency_per_sample[:-1]))) / fs
    iq = 0.5*np.exp(1j*phase)
    synthetic = waterfall_periodogram(iq, fs, fft_size, hop)
    expected_rows = 191  # Derived in lesson before execution.
    if synthetic.psd.shape != (expected_rows, fft_size) or synthetic.trailing_samples != 0:
        raise RuntimeError("Synthetic waterfall row count/shape is unexpected")
    region_start = synthetic.frame_start_samples // region_samples
    region_end = (synthetic.frame_start_samples+fft_size-1) // region_samples
    clean = region_start == region_end
    peak_frequency = synthetic.frequency_hz[np.argmax(synthetic.psd, axis=1)]
    expected_clean = region_frequency[region_start[clean]]
    np.testing.assert_array_equal(peak_frequency[clean], expected_clean)
    if np.count_nonzero(clean) != 189:
        raise RuntimeError("Expected 189 single-region and 2 transition windows")
    np.testing.assert_allclose(synthetic.psd.sum(axis=1)*(fs/fft_size), 0.25, atol=1e-13)

    capacity = 96
    history = WaterfallHistory(synthetic.frequency_hz, capacity)
    for row, time in zip(synthetic.psd, synthetic.time_seconds):
        history.append(row, time)
    history_time, history_frequency, history_psd = history.snapshot()
    np.testing.assert_array_equal(history_psd, synthetic.psd[-capacity:])
    np.testing.assert_array_equal(history_time, synthetic.time_seconds[-capacity:])
    np.testing.assert_array_equal(history_frequency, synthetic.frequency_hz)
    if history.rows_received != 191 or history.rows_evicted != 95:
        raise RuntimeError("History counters are unexpected")
    history.reset()
    history.append(synthetic.psd[0], synthetic.time_seconds[0])
    np.testing.assert_array_equal(history.snapshot()[2], synthetic.psd[:1])
    if history.rows_received != 1 or history.rows_evicted != 0:
        raise RuntimeError("Reset and replay failed")

    real_iq, metadata = load_iq_record(args.record)
    before, after = metadata["settings_before"], metadata["settings_after"]
    for key in ("sample_rate_hz", "rx_lo_hz", "rx_rf_bandwidth_hz"):
        if before[key] != after[key]:
            raise ValueError(f"Saved RX configuration changed during capture: {key}")
    real_fs = float(before["sample_rate_hz"])
    real = waterfall_periodogram(real_iq, real_fs, fft_size=256, hop_samples=128)
    # Independent weighted time-domain check for every real-data window.
    w = 0.5-0.5*np.cos(2*np.pi*np.arange(256)/256)
    expected_real_power = np.array([
        np.sum(np.abs(real_iq[start:start+256])**2*w**2)/np.sum(w**2)
        for start in real.frame_start_samples
    ])
    real_spectral_power = real.psd.sum(axis=1)*real_fs/256
    np.testing.assert_allclose(real_spectral_power, expected_real_power, rtol=1e-12)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = args.output or ROOT/"results"/f"p05a-waterfall-{stamp}"
    output.mkdir(parents=True, exist_ok=False)
    arrays = {
        "synthetic_iq": iq,
        "synthetic_frequency_per_sample_hz": frequency_per_sample,
        "synthetic_frequency_offset_hz": synthetic.frequency_hz,
        "synthetic_time_seconds": synthetic.time_seconds,
        "synthetic_frame_start_samples": synthetic.frame_start_samples,
        "synthetic_psd_normalized_squared_per_hz": synthetic.psd,
        "synthetic_single_region_mask": clean,
        "synthetic_peak_frequency_hz": peak_frequency,
        "history_time_seconds": history_time,
        "history_psd_normalized_squared_per_hz": history_psd,
        "receive_frequency_offset_hz": real.frequency_hz,
        "receive_frequency_rf_hz": float(before["rx_lo_hz"])+real.frequency_hz,
        "receive_time_seconds": real.time_seconds,
        "receive_frame_start_samples": real.frame_start_samples,
        "receive_psd_counts_squared_per_hz": real.psd,
    }
    np.savez(output/"waterfall.npz", **arrays)
    with np.load(output/"waterfall.npz", allow_pickle=False) as saved:
        for key, expected in arrays.items():
            np.testing.assert_array_equal(saved[key], expected)
        recomputed = waterfall_periodogram(saved["synthetic_iq"], fs, fft_size, hop)
        np.testing.assert_array_equal(saved["synthetic_psd_normalized_squared_per_hz"], recomputed.psd)
        real_again, meta_again = load_iq_record(args.record)
        real_recomputed = waterfall_periodogram(real_again, float(meta_again["settings_before"]["sample_rate_hz"]), 256, 128)
        np.testing.assert_array_equal(saved["receive_psd_counts_squared_per_hz"], real_recomputed.psd)

    plt.rcParams.update({"font.size": 10})
    fig, axes = plt.subplots(1, 3, figsize=(16, 6), layout="constrained")
    for axis, time, psd, title in (
        (axes[0], synthetic.time_seconds, synthetic.psd, "Simulated switches: 191 rows"),
        (axes[1], history_time, history_psd, "Latest 96 rows: 95 older rows evicted"),
    ):
        mesh = plot_waterfall(axis, synthetic.frequency_hz, time, psd, 1000, 1000,
                              "Baseband frequency (kHz)", "Sample time (ms)", title, -130, -35)
        fig.colorbar(mesh, ax=axis, label="PSD dB re 1 normalized unit^2/Hz")
        for boundary in (32, 64):
            if time[0]*1000 <= boundary <= time[-1]*1000:
                axis.axhline(boundary, color="white", linestyle="--", linewidth=0.8)
    mesh = plot_waterfall(axes[2], real.frequency_hz, real.time_seconds, real.psd, 1e6, 1e6,
                          "Baseband frequency (MHz)", "Sample time (us)",
                          f"Saved real RX: {len(real.time_seconds)} overlapping rows", -80, -30)
    fig.colorbar(mesh, ax=axes[2], label="PSD dB re 1 count^2/Hz (not dBm/dBFS)")
    fig.suptitle("P05a-2 OFFLINE waterfall | left/middle: simulation | right: short saved RX, unknown stimulus")
    fig.savefig(output/"waterfall.png", dpi=140)
    plt.close(fig)

    waterfall_periodogram(iq, fs, fft_size, hop)  # warmup not timed
    timings = []
    for _ in range(10):
        start = perf_counter()
        waterfall_periodogram(iq, fs, fft_size, hop)
        timings.append((perf_counter()-start)*1000)
    report = {
        "experiment": "P05a-2 offline waterfall and bounded history",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "hardware_contacted": False,
        "time_axis": "relative input sample time, window sample-index midpoint; not hardware or UI clock",
        "matrix_layout": "[time_row, frequency_bin]; linear two-sided PSD; no mean or noise removal",
        "synthetic": {
            "source": "known simulated piecewise-frequency tone; never transmitted",
            "sample_rate_hz": fs, "sample_count": len(iq), "duration_seconds": len(iq)/fs,
            "amplitude": 0.5, "phase_continuous": True, "added_noise": False,
            "region_duration_seconds": region_samples/fs,
            "region_frequencies_hz": region_frequency.tolist(),
            "fft_size": fft_size, "hop_samples": hop, "window": synthetic.window,
            "bin_width_hz": fs/fft_size, "row_period_seconds": hop/fs,
            "expected_rows": expected_rows, "actual_rows": len(synthetic.time_seconds),
            "single_region_rows": int(clean.sum()), "all_single_region_peaks_match": True,
            "transition_rows": np.flatnonzero(~clean).tolist(),
            "all_row_integrated_power_expected": 0.25,
            "max_row_power_error": float(np.max(np.abs(synthetic.psd.sum(axis=1)*fs/fft_size-0.25))),
            "trailing_samples": synthetic.trailing_samples,
        },
        "display_history": {
            "capacity_rows": capacity, "received_rows_before_reset": 191,
            "retained_rows_before_reset": len(history_time), "evicted_rows_before_reset": 95,
            "last_rows_and_times_exact_match": True, "reset_and_restart_reference_passed": True,
            "eviction_is_not_adc_sample_loss": True,
            "this_is_offline_row_replay_not_live_gui_refresh": True,
        },
        "saved_receive": {
            "source": "one previously saved real RX frame; unknown stimulus",
            "record_directory": str(args.record.resolve()), "capture_id": metadata["capture_id"],
            "sample_sha256": metadata["sample_sha256"], "sample_count": len(real_iq),
            "sample_rate_hz": real_fs, "duration_seconds": len(real_iq)/real_fs,
            "rx_lo_hz": before["rx_lo_hz"], "rx_rf_bandwidth_hz": before["rx_rf_bandwidth_hz"],
            "gain_control_mode": before["gain_control_mode"],
            "gain_readback_db_before": before["gain_readback_db"], "gain_readback_db_after": after["gain_readback_db"],
            "fft_size": real.fft_size, "hop_samples": real.hop_samples,
            "row_count": len(real.time_seconds), "bin_width_hz": real_fs/real.fft_size,
            "row_period_seconds": real.hop_samples/real_fs,
            "trailing_samples": real.trailing_samples,
            "max_weighted_parseval_error": float(np.max(np.abs(real_spectral_power-expected_real_power))),
            "psd_units": "raw receive counts squared/Hz; not dBm/dBFS",
            "separate_captures_stitched": False, "samples_duplicated_to_fake_duration": False,
            "long_duration_or_live_capture_verified": False, "modulation_label": None,
        },
        "saved_arrays_reload_and_recompute_exact_match": True,
        "runtime": {"python": platform.python_version(), "numpy": np.__version__, "os": platform.platform()},
        "desktop_batch_timing": {
            "repetitions": len(timings), "median_ms": float(np.median(timings)), "max_ms": max(timings),
            "scope": "entire 98304-sample/191-row waterfall reference only; excludes IO, plot and acquisition",
            "board_or_continuous_throughput_measurement": False,
        },
        "source_code_sha256": {str(path.relative_to(ROOT)): sha256(path) for path in (
            Path(__file__), ROOT/"src"/"rfsig"/"waterfall.py", ROOT/"src"/"rfsig"/"spectrum.py", ROOT/"tests"/"test_waterfall.py")},
        "result_sha256": {name: sha256(output/name) for name in ("waterfall.npz", "waterfall.png")},
        "remaining": ["continuous real RX with sample/gap tracking", "live GUI refresh",
                      "P05b physical parameter estimators", "FPGA/ARM implementation and board validation"],
    }
    (output/"report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "synthetic": report["synthetic"],
                      "display_history": report["display_history"], "saved_receive": report["saved_receive"],
                      "desktop_batch_timing": report["desktop_batch_timing"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
