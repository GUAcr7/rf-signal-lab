"""Validate equal-tail bandwidth on saved modulation references and old RX."""

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from time import perf_counter

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from rfsig.bandwidth import occupied_bandwidth
from rfsig.iq_recording import load_iq_record
from rfsig.spectrum import power_periodogram


ROOT = Path(__file__).resolve().parents[1]
REFERENCES = {
    "BPSK": "p04-bpsk-20261003T102947621995Z",
    "QPSK": "p04-qpsk-20261003T103128391971Z",
    "16QAM": "p04-16qam-20261003T103357180550Z",
}


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def ideal_rc_half_width(symbol_rate, beta, fraction=0.99):
    """Independent analytic integral of ideal raised-cosine PSD tail.

    Normalized positive rolloff tail is beta/2*(u-sin(pi*u)/pi),
    u=(support_edge-f)/(beta*Rs). This is not discrete CDF interpolation.
    """
    tail = (1-fraction)/2
    if beta == 0 or tail >= beta/2:
        return fraction*symbol_rate/2
    low, high = 0., 1.
    for _ in range(80):
        u = (low+high)/2
        power = beta/2*(u-math.sin(math.pi*u)/math.pi)
        if power < tail:
            low = u
        else:
            high = u
    return (1+beta)*symbol_rate/2-beta*symbol_rate*(low+high)/2


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = args.output or ROOT/"results"/f"p05b-bandwidth-{stamp}"
    output.mkdir(parents=True, exist_ok=False)
    arrays, measurements = {}, []
    plot_cases = []
    for label, name in REFERENCES.items():
        directory = ROOT/"results"/name
        metadata = json.loads((directory/"metadata.json").read_text(encoding="utf-8"))
        if sha256(directory/"reference.npz") != metadata["npz_sha256"]:
            raise ValueError(f"Reference data hash differs: {label}")
        with np.load(directory/"reference.npz", allow_pickle=False) as saved:
            iq = saved["shaped_iq"].copy()
        fs = metadata["sample_rate_hz"]
        spectrum = power_periodogram(iq, fs)
        roi = (-250_000., 250_000.)
        measured = occupied_bandwidth(spectrum.frequency_hz, spectrum.psd, roi, rf_lo_hz=0)
        expected_half = ideal_rc_half_width(metadata["symbol_rate_hz"], metadata["rolloff"])
        relative_error = abs(measured.bandwidth_hz-2*expected_half)/(2*expected_half)
        # Fixed before executing: finite random record/truncated FIR tolerance.
        if relative_error > 0.05 or abs(measured.center_baseband_hz) > 5000:
            raise RuntimeError(f"{label} exceeds 5% width / 5 kHz zero-center reference tolerance")
        shift = 1000*fs/len(iq)  # Exact FFT-bin shift; keeps signal inside ROI.
        shifted_iq = iq*np.exp(2j*np.pi*1000*np.arange(len(iq))/len(iq))
        shifted = power_periodogram(shifted_iq, fs)
        shifted_band = occupied_bandwidth(shifted.frequency_hz, shifted.psd,
                                          (roi[0]+shift, roi[1]+shift), rf_lo_hz=0)
        np.testing.assert_allclose(shifted_band.bandwidth_hz, measured.bandwidth_hz, atol=1e-6, rtol=0)
        np.testing.assert_allclose(shifted_band.center_baseband_hz-measured.center_baseband_hz, shift, atol=1e-6, rtol=0)
        measurements.append({
            "label_from_source_metadata_not_ai_prediction": label,
            "source": "P04 Python simulation, never transmitted",
            "record_directory": str(directory), "npz_sha256": metadata["npz_sha256"],
            "sample_rate_hz": fs, "sample_count": len(iq), "window": spectrum.window,
            "bin_width_hz": spectrum.bin_width_hz, "measurement": asdict(measured),
            "symbol_rate_hz": metadata["symbol_rate_hz"], "rolloff": metadata["rolloff"],
            "ideal_rc_99_bandwidth_hz": 2*expected_half,
            "ideal_rrc_support_width_hz": metadata["ideal_rrc_support_total_hz"],
            "relative_width_error_vs_ideal_rc": relative_error,
            "finite_record_width_tolerance": 0.05, "center_tolerance_hz": 5000,
            "fft_bin_shift_hz": shift, "shifted_measurement": asdict(shifted_band),
            "shift_width_and_center_error_tolerance_hz": 1e-6,
            "physical_rf_accuracy_verified": False,
        })
        arrays[f"{label}_frequency_hz"] = spectrum.frequency_hz
        arrays[f"{label}_psd"] = spectrum.psd
        arrays[f"{label}_shifted_psd"] = shifted.psd
        plot_cases.append((label+" simulated | normalized units", spectrum, measured, expected_half, 1000, "Frequency offset (kHz)"))

    record = ROOT/"results"/"p02-20261003T100526764044Z"
    iq, metadata = load_iq_record(record)
    config = metadata["settings_before"]
    spectrum = power_periodogram(iq, config["sample_rate_hz"])
    real_band = occupied_bandwidth(spectrum.frequency_hz, spectrum.psd, (-9e6, 9e6), rf_lo_hz=config["rx_lo_hz"])
    real = {
        "source": "saved real RX, unknown stimulus; spectral distribution only",
        "record_directory": str(record), "sample_sha256": metadata["sample_sha256"],
        "settings_before": config, "settings_after": metadata["settings_after"],
        "sample_count": len(iq), "window": spectrum.window,
        "measurement": asdict(real_band), "psd_units": "raw counts squared/Hz",
        "known_target_detected": False, "physical_center_or_bandwidth_accuracy_verified": False,
        "noise_floor_measured": False, "physical_rf_axis_direction_verified": False,
    }
    arrays["real_frequency_hz"], arrays["real_psd"] = spectrum.frequency_hz, spectrum.psd
    plot_cases.append(("Saved real RX | unknown target | counts", spectrum, real_band, None, 1e6, "Frequency offset (MHz)"))
    np.savez(output/"bandwidth_reference.npz", **arrays)
    with np.load(output/"bandwidth_reference.npz", allow_pickle=False) as saved:
        for name, value in arrays.items():
            np.testing.assert_array_equal(saved[name], value)
        again = occupied_bandwidth(saved["real_frequency_hz"], saved["real_psd"], (-9e6, 9e6), rf_lo_hz=config["rx_lo_hz"])
        if again != real_band:
            raise RuntimeError("Saved spectrum bandwidth does not replay exactly")

    fig, axes = plt.subplots(2, 2, figsize=(12, 8), layout="constrained")
    for axis, (title, spec, band, expected_half, scale, xlabel) in zip(axes.flat, plot_cases):
        axis.plot(spec.frequency_hz/scale, 10*np.log10(np.maximum(spec.psd, 1e-16)), linewidth=0.8)
        axis.axvspan(band.lower_hz/scale, band.upper_hz/scale, color="orange", alpha=0.2, label="Measured 99% interval")
        axis.axvline(band.center_baseband_hz/scale, color="red", linestyle="--", label="Boundary midpoint")
        if expected_half is not None:
            for sign in (-1, 1):
                axis.axvline(sign*expected_half/scale, color="green", linestyle=":")
            axis.set_xlim(-150, 150)
            axis.set_ylim(-110, -35)
        axis.set(title=f"{title}\nWidth={band.bandwidth_hz/scale:.3f}, center={band.center_baseband_hz/scale:.3f}",
                 xlabel=xlabel, ylabel="PSD dB re 1 input unit^2/Hz (not dBm)")
        axis.grid(alpha=0.3)
        axis.legend(fontsize=8)
    fig.suptitle("P05b-2 OFFLINE 99% equal-tail bandwidth | ROI and noise policy recorded")
    fig.savefig(output/"bandwidth_reference.png", dpi=140)
    plt.close(fig)
    timings = []
    occupied_bandwidth(spectrum.frequency_hz, spectrum.psd, (-9e6, 9e6))
    for _ in range(50):
        start = perf_counter()
        occupied_bandwidth(spectrum.frequency_hz, spectrum.psd, (-9e6, 9e6))
        timings.append((perf_counter()-start)*1000)
    report = {
        "experiment": "P05b-2 equal-tail bandwidth and spectral midpoint, offline reference",
        "created_utc": datetime.now(timezone.utc).isoformat(), "hardware_contacted": False,
        "definition": "0.5%-99.5% equal-tail interval of effective linear PSD in explicit ROI; midpoint is spectral center",
        "interpolation": "piecewise-constant PSD in bin-centered cells, including clipped ROI cells",
        "noise_policy": "no subtraction on these input records; no target detection implied",
        "simulated_modulation": measurements, "saved_receive": real,
        "saved_array_reload_and_bandwidth_replay_passed": True,
        "desktop_timing": {"repetitions": 50, "median_ms": float(np.median(timings)), "max_ms": max(timings),
                           "scope": "1024-point PSD-to-bandwidth only; excludes FFT, IO, plotting and acquisition"},
        "source_code_sha256": {str(path.relative_to(ROOT)): sha256(path) for path in (
            Path(__file__), ROOT/"src"/"rfsig"/"bandwidth.py", ROOT/"tests"/"test_bandwidth.py")},
        "result_sha256": {name: sha256(output/name) for name in ("bandwidth_reference.npz", "bandwidth_reference.png")},
        "remaining": ["known RF accuracy validation", "FPGA/ARM implementation", "GUI and continuous receive integration"],
    }
    (output/"report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "simulated_modulation": measurements, "saved_receive": real,
                      "desktop_timing": report["desktop_timing"]}, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
