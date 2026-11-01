"""Plot/check a known tone and a saved RX frame without accessing hardware."""

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
from rfsig.spectrum import power_periodogram
from rfsig.tone import complex_tone


ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def statistics(iq, fs):
    result = power_periodogram(iq, fs)
    integrated = float(result.bin_power.sum())
    error = integrated - result.window_weighted_mean_power
    np.testing.assert_allclose(integrated, result.window_weighted_mean_power, rtol=1e-12, atol=1e-14)
    return result, {
        "sample_count": result.sample_count,
        "sample_rate_hz": fs,
        "sample_duration_seconds": len(iq)/fs,
        "bin_width_hz": result.bin_width_hz,
        "window": result.window,
        "unweighted_time_mean_power": result.time_mean_power,
        "window_weighted_mean_power": result.window_weighted_mean_power,
        "integrated_spectral_power": integrated,
        "weighted_parseval_error": error,
        "largest_bin_offset_hz": float(result.frequency_hz[np.argmax(result.psd)]) if integrated > 0 else None,
        "largest_bin_is_not_center_frequency_estimate": True,
        "input_mean_removed": False,
        "input_amplitude_normalized": False,
        "noise_floor_removed": False,
        "hardware_contacted": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--record", type=Path, default=ROOT/"results"/"p02-20261003T100526764044Z")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    # Existing helper verifies file SHA256, dtype, sample count and metadata.
    real_iq, metadata = load_iq_record(args.record)
    before, after = metadata["settings_before"], metadata["settings_after"]
    for key in ("sample_rate_hz", "rx_lo_hz", "rx_rf_bandwidth_hz"):
        if before[key] != after[key]:
            raise ValueError(f"Saved RX configuration changed during capture: {key}")
    fs = float(before["sample_rate_hz"])
    lo = float(before["rx_lo_hz"])
    real_result, real_stats = statistics(real_iq, fs)
    tone_fs, count, offset, amplitude = 30_720_000, 1024, 960_000, 0.5
    tone_iq = complex_tone(tone_fs, count, offset, amplitude)
    tone_result, tone_stats = statistics(tone_iq, tone_fs)
    assert tone_stats["largest_bin_offset_hz"] == offset
    np.testing.assert_allclose(tone_stats["integrated_spectral_power"], amplitude**2, atol=1e-14)
    tone_stats.update({"expected_offset_hz": offset, "expected_total_power": 0.25,
                       "source": "synthetic_known_tone_not_rf_capture"})
    real_stats.update({
        "source": "previously_saved_real_receive_frame_unknown_stimulus",
        "record_directory": str(args.record.resolve()),
        "capture_id": metadata["capture_id"],
        "sample_sha256": metadata["sample_sha256"],
        "rx_lo_hz": lo,
        "rx_rf_bandwidth_hz": before["rx_rf_bandwidth_hz"],
        "gain_control_mode": before["gain_control_mode"],
        "gain_readback_db_before": before["gain_readback_db"],
        "gain_readback_db_after": after["gain_readback_db"],
        "modulation_label": None,
        "sample_units": metadata["sample_units"],
        "psd_units": "raw receive counts squared/Hz; not dBm or dBFS",
        "physical_rf_axis_direction_verified_by_this_experiment": False,
    })

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = args.output or ROOT/"results"/f"p05a-spectrum-{stamp}"
    output.mkdir(parents=True, exist_ok=False)
    arrays = {
        "tone_frequency_offset_hz": tone_result.frequency_hz,
        "tone_psd_normalized_squared_per_hz": tone_result.psd,
        "receive_frequency_offset_hz": real_result.frequency_hz,
        "receive_frequency_rf_hz": lo+real_result.frequency_hz,
        "receive_psd_counts_squared_per_hz": real_result.psd,
    }
    np.savez(output/"spectrum.npz", **arrays)
    # Reload independently and compute from input again; do not compare images.
    real_again, meta_again = load_iq_record(args.record)
    recomputed = power_periodogram(real_again, float(meta_again["settings_before"]["sample_rate_hz"]))
    with np.load(output/"spectrum.npz", allow_pickle=False) as saved:
        for key, value in arrays.items():
            np.testing.assert_array_equal(saved[key], value)
        np.testing.assert_array_equal(saved["receive_psd_counts_squared_per_hz"], recomputed.psd)
        np.testing.assert_array_equal(saved["receive_frequency_offset_hz"], recomputed.frequency_hz)

    fig, axes = plt.subplots(2, 2, figsize=(12, 7), layout="constrained")
    for column, (iq, rate, result, name, unit) in enumerate([
        (tone_iq, tone_fs, tone_result, "Known synthetic tone (+960 kHz)", "Normalized amplitude"),
        (real_iq, fs, real_result, "Saved real RX frame (unknown stimulus)", "Raw receive counts"),
    ]):
        shown = min(128, len(iq))
        axes[0, column].plot(np.arange(shown)/rate*1e6, iq[:shown].real, label="I")
        axes[0, column].plot(np.arange(shown)/rate*1e6, iq[:shown].imag, label="Q")
        axes[0, column].set(title=name, xlabel="Time (us)", ylabel=unit)
        axes[0, column].legend()
        # Clip only the plotted logarithm. Linear NPZ preserves all zero bins.
        db = 10*np.log10(np.maximum(result.psd, 1e-16))
        axes[1, column].plot(result.frequency_hz/1e6, db)
        label = "PSD dB re 1 normalized unit^2/Hz" if column == 0 else "PSD dB re 1 count^2/Hz (not dBm/dBFS)"
        axes[1, column].set(title=f"Periodic Hann | {result.sample_count} points | {result.bin_width_hz/1e3:g} kHz/bin",
                            xlabel="Baseband frequency offset (MHz)", ylabel=label)
    axes[1, 0].axvline(offset/1e6, linestyle="--", color="orange", label="Expected +0.96 MHz")
    axes[1, 0].legend()
    for axis in axes.flat:
        axis.grid(alpha=0.3)
    fig.suptitle("P05a-1 OFFLINE spectrum reference | no board configuration or transmission")
    fig.savefig(output/"spectrum.png", dpi=140)
    plt.close(fig)

    power_periodogram(real_iq, fs)  # Warm up, excluded from timing.
    timings = []
    for _ in range(50):
        start = perf_counter()
        power_periodogram(real_iq, fs)
        timings.append((perf_counter()-start)*1000)
    report = {
        "experiment": "P05a-1 offline spectrum reference",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "tone": tone_stats,
        "saved_receive": real_stats,
        "npz_reload_and_recompute_exact_match": True,
        "plot_db_floor": -160,
        "runtime": {"python": platform.python_version(), "numpy": np.__version__, "os": platform.platform()},
        "desktop_analysis_timing": {
            "repetitions": len(timings), "median_ms": float(np.median(timings)), "max_ms": max(timings),
            "scope": "saved-frame power_periodogram only; excludes IO, plotting, transfer and acquisition",
            "board_or_continuous_throughput_measurement": False,
        },
        "source_code_sha256": {str(path.relative_to(ROOT)): sha256(path) for path in (
            Path(__file__), ROOT/"src"/"rfsig"/"spectrum.py", ROOT/"tests"/"test_spectrum.py")},
        "result_sha256": {name: sha256(output/name) for name in ("spectrum.npz", "spectrum.png")},
        "remaining": ["waterfall and continuous refresh", "P05b parameter estimators", "FPGA/ARM implementation",
                      "controlled RF accuracy validation", "Vivado account approval/download/install"],
    }
    (output/"report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "tone": tone_stats, "saved_receive": real_stats,
                      "desktop_analysis_timing": report["desktop_analysis_timing"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
