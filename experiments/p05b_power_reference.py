"""Offline digital power reference; no RF stimulus or receiver configuration."""

import argparse
from datetime import datetime, timezone
from fractions import Fraction
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
from rfsig.power import mean_iq_power, power_db
from rfsig.spectrum import power_periodogram


ROOT = Path(__file__).resolve().parents[1]
RAW_UNITS = "unscaled raw receive counts; not volts or dBm"


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def db_report(value, reference):
    measured = power_db(value, reference)
    return {"value_db": None if value == 0 else measured,
            "status": "zero_power" if value == 0 else "finite",
            "mathematical_zero_power_db": "negative infinity" if value == 0 else None,
            "reference_power": reference}


def analyze_record(directory):
    iq, metadata = load_iq_record(directory)
    if metadata.get("sample_units") != RAW_UNITS:
        raise ValueError("This experiment expects the P02 unscaled raw receive counts format")
    if not np.all(iq.real == np.rint(iq.real)) or not np.all(iq.imag == np.rint(iq.imag)):
        raise ValueError("Raw-count input contains noninteger samples; check scale metadata")
    value = mean_iq_power(iq)
    # Python integer arithmetic and exact Fraction are independent of NumPy.
    total_squared_counts = sum(int(x.real)**2+int(x.imag)**2 for x in iq)
    exact = Fraction(total_squared_counts, len(iq))
    np.testing.assert_allclose(value, float(exact), rtol=1e-14, atol=1e-14)
    before, after = metadata["settings_before"], metadata["settings_after"]
    spectrum = power_periodogram(iq, float(before["sample_rate_hz"]), "rectangular")
    spectral_power = float(spectrum.bin_power.sum())
    np.testing.assert_allclose(spectral_power, value, rtol=1e-12, atol=1e-14)
    return iq, metadata, {
        "source": "previously_saved_real_receive_frame_unknown_stimulus",
        "record_directory": str(directory.resolve()), "capture_id": metadata["capture_id"],
        "sample_sha256": metadata["sample_sha256"], "sample_count": len(iq),
        "sample_units": metadata["sample_units"], "power_units": "raw receive counts squared",
        "mean_digital_power": value,
        "exact_integer_reference": {"squared_count_sum": total_squared_counts,
                                    "sample_count": len(iq), "fraction": str(exact),
                                    "mean_power": float(exact)},
        "db_relative_to_one_count_squared": db_report(value, 1.0),
        "rectangular_spectral_integral": spectral_power,
        "rectangular_parseval_absolute_error": abs(spectral_power-value),
        "settings_before": before, "settings_after": after,
        "scan_format": metadata["scan_format"],
        "normalized_before_measurement": False,
        "mean_or_noise_removed": False,
        "contains_signal_noise_dc_and_spurs_without_separation": True,
        "hardware_state_rechecked_this_run": False,
        "modulation_label": None,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference-record", type=Path, default=ROOT/"results"/"p02-20261003T100526764044Z")
    parser.add_argument("--comparison-record", type=Path, default=ROOT/"results"/"p02-20261003T100528622563Z")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    amplitudes = np.array([0., 0.125, 0.25, 0.5, 1.])
    unit_tone = np.tile(np.array([1, 1j, -1, -1j], dtype=complex), 256)
    synthetic_iq = amplitudes[:, None]*unit_tone[None, :]
    synthetic_power = np.array([mean_iq_power(row) for row in synthetic_iq])
    expected_power = np.array([0., 0.015625, 0.0625, 0.25, 1.])
    expected_finite_db = np.array([-12.041199826559248, -6.020599913279624, 0., 6.020599913279624])
    synthetic_db = np.array([power_db(value, 0.25) for value in synthetic_power])
    np.testing.assert_array_equal(synthetic_power, expected_power)
    np.testing.assert_allclose(synthetic_db[1:], expected_finite_db, atol=1e-12)
    if synthetic_db[0] != -np.inf:
        raise RuntimeError("Zero input must return negative infinity before report formatting")

    first_iq, first_meta, first = analyze_record(args.reference_record)
    second_iq, second_meta, second = analyze_record(args.comparison_record)
    if first_meta["scan_format"] != second_meta["scan_format"]:
        raise ValueError("Raw-count scan formats differ; do not compare their numerical scale silently")
    first_power, second_power = first["mean_digital_power"], second["mean_digital_power"]
    if first_power == 0:
        raise ValueError("Reference capture has zero power; choose a positive fixed power reference")
    difference = db_report(second_power, first_power)
    halved_iq = 0.5*first_iq
    halved_power = mean_iq_power(halved_iq)
    halved_difference = power_db(halved_power, first_power)
    np.testing.assert_allclose(halved_power, first_power/4, rtol=1e-14)
    np.testing.assert_allclose(halved_difference, -6.020599913279624, atol=1e-12)

    setting_keys = ("sample_rate_hz", "rx_lo_hz", "rx_rf_bandwidth_hz")
    condition_checks = {
        "receiver_settings_equal_and_stable_in_saved_snapshots": all(
            first_meta["settings_before"][key] == first_meta["settings_after"][key]
            == second_meta["settings_before"][key] == second_meta["settings_after"][key]
            for key in setting_keys),
        "both_gain_modes_manual": all(meta[side]["gain_control_mode"] == "manual"
                                      for meta in (first_meta, second_meta)
                                      for side in ("settings_before", "settings_after")),
        "gain_readbacks_equal_in_saved_snapshots": len({meta[side]["gain_readback_db"]
                                                       for meta in (first_meta, second_meta)
                                                       for side in ("settings_before", "settings_after")}) == 1,
        "known_rf_input_and_attenuation_change_verified": False,
        "analog_linearity_noise_and_calibration_verified": False,
    }

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = args.output or ROOT/"results"/f"p05b-power-{stamp}"
    output.mkdir(parents=True, exist_ok=False)
    arrays = {
        "synthetic_amplitudes": amplitudes, "synthetic_iq": synthetic_iq,
        "synthetic_mean_power": synthetic_power, "synthetic_relative_db": synthetic_db,
        "saved_reference_iq": first_iq, "saved_comparison_iq": second_iq,
        "offline_halved_reference_iq": halved_iq,
    }
    np.savez(output/"power_reference.npz", **arrays)
    with np.load(output/"power_reference.npz", allow_pickle=False) as saved:
        for key, value in arrays.items():
            np.testing.assert_array_equal(saved[key], value)
        np.testing.assert_array_equal([mean_iq_power(row) for row in saved["synthetic_iq"]], expected_power)
        np.testing.assert_allclose(mean_iq_power(saved["offline_halved_reference_iq"]), first_power/4, rtol=1e-14)
    first_again, _ = load_iq_record(args.reference_record)
    second_again, _ = load_iq_record(args.comparison_record)
    if mean_iq_power(first_again) != first_power or mean_iq_power(second_again) != second_power:
        raise RuntimeError("Independent saved-capture reload changed the mean power")

    fig, axes = plt.subplots(1, 3, figsize=(14, 4.5), layout="constrained")
    theory_amplitude = np.linspace(0, 1, 200)
    axes[0].plot(theory_amplitude, theory_amplitude**2, linestyle="--", label="Theory P=A^2")
    axes[0].scatter(amplitudes, synthetic_power, color="orange", label="Reference calculation")
    axes[0].set(title="Synthetic constant-amplitude IQ", xlabel="Amplitude A", ylabel="Power (normalized unit^2)")
    axes[0].legend()
    ratio = amplitudes[1:]/0.5
    axes[1].plot(ratio, synthetic_db[1:], marker="o")
    axes[1].set(title="Explicit reference: P_ref=0.25", xlabel="Amplitude / reference amplitude", ylabel="Relative power (dB)")
    axes[1].set_xticks(ratio)
    axes[1].annotate("Zero power: -infinity dB", xy=(0.04, 0.93), xycoords="axes fraction", fontsize=9)
    bars = axes[2].bar(["Saved A", "A x 0.5\n(offline)", "Saved B"], [first_power, halved_power, second_power], color=["tab:blue", "tab:orange", "tab:green"])
    axes[2].bar_label(bars, fmt="%.2f", padding=3)
    axes[2].set(title="Raw counts: AGC, unknown RF input", ylabel="Mean digital power (count^2)")
    axes[2].set_ylim(0, 1.2*max(first_power, second_power))
    for axis in axes:
        axis.grid(alpha=0.3, axis="y")
    fig.suptitle("P05b-1 OFFLINE digital power | no RF attenuation sweep | no dBm calibration")
    fig.savefig(output/"power_reference.png", dpi=140)
    plt.close(fig)

    power_db(mean_iq_power(first_iq), 1.0)  # warmup excluded
    timings = []
    for _ in range(100):
        start = perf_counter()
        power_db(mean_iq_power(first_iq), 1.0)
        timings.append((perf_counter()-start)*1000)
    report = {
        "experiment": "P05b-1 offline digital power and explicit reference",
        "created_utc": datetime.now(timezone.utc).isoformat(), "hardware_contacted": False,
        "measurement_definition": "unwindowed mean(I^2+Q^2), no DC/noise removal or AI normalization",
        "absolute_rf_dbm_calibrated": False, "dbfs_reference_defined": False,
        "synthetic": {
            "source": "Python four-phase constant-amplitude tone, never transmitted",
            "sample_rate_hz": 1_024_000, "sample_count_per_case": len(unit_tone), "tone_frequency_hz": 256_000,
            "amplitudes": amplitudes.tolist(), "mean_power": synthetic_power.tolist(),
            "expected_power": expected_power.tolist(),
            "db_relative_to_fixed_power_0_25": [db_report(value, 0.25) for value in synthetic_power],
            "all_theoretical_checks_passed": True,
        },
        "reference_capture": first, "comparison_capture": second,
        "digital_comparison": {
            "reference_capture_id": first_meta["capture_id"],
            "comparison_capture_id": second_meta["capture_id"],
            "db_relative_to_reference_capture": difference,
            "numerical_raw_count_comparison_valid": True,
            "rf_power_change_validation_passed": False,
            "condition_checks": condition_checks,
            "limitation": "AGC snapshots and unknown input; no fixed-gain known attenuation or analog calibration validation",
        },
        "offline_scaling_check": {
            "source": "mathematical copy of saved reference IQ, not a new RF capture",
            "amplitude_scale": 0.5, "expected_power_ratio": 0.25,
            "actual_power_ratio": halved_power/first_power, "mean_power": halved_power,
            "relative_db": halved_difference, "expected_relative_db": -6.020599913279624,
        },
        "saved_arrays_and_independent_capture_replay_passed": True,
        "runtime": {"python": platform.python_version(), "numpy": np.__version__, "os": platform.platform()},
        "desktop_timing": {"repetitions": len(timings), "median_ms": float(np.median(timings)), "max_ms": max(timings),
                           "scope": "1024-sample mean_iq_power and power_db only; excludes IO, spectrum, plot, acquisition",
                           "board_or_continuous_throughput_measurement": False},
        "source_code_sha256": {str(path.relative_to(ROOT)): sha256(path) for path in (
            Path(__file__), ROOT/"src"/"rfsig"/"power.py", ROOT/"src"/"rfsig"/"spectrum.py", ROOT/"tests"/"test_power.py")},
        "result_sha256": {name: sha256(output/name) for name in ("power_reference.npz", "power_reference.png")},
        "remaining": ["fixed-gain known RF attenuation validation", "99 percent occupied bandwidth and spectral center",
                      "FPGA/ARM implementation and board comparison", "live UI integration"],
    }
    (output/"report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "first_power_counts_squared": first_power,
                      "second_power_counts_squared": second_power, "digital_comparison": report["digital_comparison"],
                      "offline_scaling_check": report["offline_scaling_check"], "desktop_timing": report["desktop_timing"]},
                     ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
