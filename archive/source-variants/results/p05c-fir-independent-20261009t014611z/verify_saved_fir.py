"""Independent saved-output audit. No project algorithm import or hardware access.

Reads the fixed final P05c export and old P04 sources. Writes only beside this
script. Full positive response is checked by direct complex exponential sums.
"""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import numpy as np


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
EXPORT = ROOT / "results" / "p05c-fir-20261009T014535083634Z"
CHECKS = []


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(name, passed, **details):
    CHECKS.append({"name": name, "passed": bool(passed), **details})


def close(name, actual, expected, atol=5e-14, rtol=5e-14):
    actual, expected = np.asarray(actual), np.asarray(expected)
    same_shape = actual.shape == expected.shape
    error = float(np.max(np.abs(actual - expected))) if same_shape and actual.size else 0.0
    check(name, same_shape and np.allclose(actual, expected, atol=atol, rtol=rtol),
          max_absolute_error=error, actual_shape=list(actual.shape), expected_shape=list(expected.shape))


def shifted_sum(iq, taps):
    output = np.zeros(len(iq) + len(taps) - 1, dtype=np.complex128)
    for lag in range(len(taps)):
        output[lag:lag + len(iq)] += iq * taps[lag]
    return output


def response_sum(taps, frequencies, rate):
    frequency = np.asarray(frequencies, dtype=np.float64)
    result = np.empty(frequency.shape, dtype=np.complex128)
    lag = np.arange(len(taps), dtype=np.float64)
    for start in range(0, frequency.size, 2048):
        stop = min(start + 2048, frequency.size)
        result[start:stop] = np.exp((-2j * np.pi / rate) * frequency[start:stop, None] * lag) @ taps
    return result


def main():
    report = json.loads((EXPORT / "report.json").read_text(encoding="utf-8"))
    check("export_archive_hash", sha(EXPORT / "reference.npz") == report["arrays_sha256"])
    check("scope_no_board_tx_live_filter_fpga_ai", all(report[key] is False for key in
          ("board_accessed", "rf_configuration_written", "tx_started", "live_receiver_filter_connected", "fpga_implemented", "ai_connected")))
    for name, expected in report["source_code_sha256"].items():
        check("current_source_hash:" + name, sha(ROOT / name) == expected)
    for source, names in report["source_file_sha256"].items():
        for name, expected in names.items():
            check("old_source_hash:" + source + "/" + name, sha(ROOT / "results" / source / name) == expected)
    with np.load(EXPORT / "reference.npz", allow_pickle=False) as saved:
        arrays = {key: saved[key].copy() for key in saved.files}
    for key, values in arrays.items():
        check("finite_array:" + key, np.isfinite(values).all(), shape=list(values.shape), dtype=str(values.dtype))

    spec = report["specification"]
    rate, count, delay = 1_000_000, 63, 31
    check("fixed_design_contract", spec == {
        "sample_rate_hz": rate, "pass_edge_hz": 100000, "stop_edge_hz": 200000,
        "sinc_cutoff_hz": 150000, "tap_count": count, "window": "symmetric Hamming",
        "max_pass_deviation_db": .1, "max_pass_ripple_db": .1,
        "min_stop_attenuation_db": 50.0, "max_waveform_nrmse": .01})
    taps = arrays["taps"]
    check("real_63_taps", taps.shape == (count,) and not np.iscomplexobj(taps))
    close("tap_symmetry", taps, taps[::-1], atol=1e-15, rtol=0)
    close("dc_unit_gain", np.sum(taps), 1.0, atol=1e-14, rtol=0)
    check("linear_phase_delay_contract", report["group_delay_samples"] == delay and report["group_delay_seconds"] == delay / rate)
    offset = np.arange(count) - delay
    sinc = np.zeros(count)
    sinc[offset == 0] = .3
    nonzero = offset != 0
    sinc[nonzero] = np.sin(.3 * np.pi * offset[nonzero]) / (np.pi * offset[nonzero])
    manual_taps = sinc * (.54 - .46 * np.cos(2 * np.pi * np.arange(count) / (count - 1)))
    manual_taps /= manual_taps.sum()
    close("independent_sine_hamming_coefficients", taps, manual_taps, atol=2e-16, rtol=1e-13)

    frequency = arrays["response_frequency_hz"]
    nfft = report["measured_response"]["nfft"]
    close("complete_positive_fft_grid", frequency, np.arange(nfft // 2 + 1) * rate / nfft, atol=1e-10, rtol=0)
    full_direct = response_sum(taps, frequency, rate)
    close("every_positive_bin_direct_response", arrays["response"], full_direct, atol=5e-14, rtol=1e-12)
    edges = arrays["exact_edge_frequency_hz"]
    close("exact_edge_frequencies", edges, [0, 84375, 100000, 150000, 200000, 500000], atol=0, rtol=0)
    exact_direct = response_sum(taps, edges, rate)
    close("exact_edge_response", arrays["exact_edge_response"], exact_direct, atol=5e-14, rtol=1e-12)
    close("negative_edge_conjugate_symmetry", response_sum(taps, -edges, rate), np.conj(exact_direct), atol=1e-14, rtol=0)
    combined_f = np.concatenate((frequency, edges))
    combined_response = np.concatenate((full_direct, exact_direct))
    db = 20 * np.log10(np.maximum(np.abs(combined_response), 1e-300))
    pass_db, stop_db = db[combined_f <= 100000], db[combined_f >= 200000]
    metrics = {"pass_max_abs_db": float(np.max(np.abs(pass_db))),
               "pass_peak_to_peak_db": float(np.ptp(pass_db)),
               "stop_min_attenuation_db": float(-np.max(stop_db))}
    check("pass_absolute_deviation_spec", metrics["pass_max_abs_db"] <= .1)
    check("pass_peak_to_peak_spec", metrics["pass_peak_to_peak_db"] <= .1)
    check("stop_attenuation_spec", metrics["stop_min_attenuation_db"] >= 50)
    for key, value in metrics.items():
        close("reported_response_metric:" + key, report["measured_response"][key], value, atol=1e-10, rtol=0)

    waveform_metrics = {}
    for row in report["waveforms"]:
        label, source = row["modulation"], ROOT / row["source_record"]
        metadata = json.loads((source / "metadata.json").read_text(encoding="utf-8"))
        check("p04_source_contract:" + label, metadata["source"] == "python_simulation_not_rf_capture" and
              metadata["modulation"] == label and metadata["sample_rate_hz"] == rate and
              metadata["symbol_rate_hz"] == 125000 and metadata["rolloff"] == .35 and
              metadata["snr_db"] is None and metadata["snr_note"] == "No noise added; no RF SNR measured")
        check("p04_metadata_archive_hash:" + label, sha(source / "reference.npz") == metadata["npz_sha256"])
        with np.load(source / "reference.npz", allow_pickle=False) as old:
            original = old["shaped_iq"].copy()
        prefix = label.lower()
        x, output = arrays[prefix + "_input"], arrays[prefix + "_output_full"]
        close("original_source_array_unchanged:" + label, x, original, atol=0, rtol=0)
        check("full_output_length:" + label, len(x) == 16457 and len(output) == len(x) + count - 1 == 16519 and
              row["input_count"] == len(x) and row["full_output_count"] == len(output))
        reference = shifted_sum(original, taps)
        close("independent_full_convolution:" + label, output, reference)
        close("saved_streaming_tail_output:" + label, arrays[prefix + "_output_blocks_with_tail"], reference)
        aligned = reference[delay:delay + len(x)]
        close("exact_31_sample_alignment:" + label, arrays[prefix + "_output_aligned"], aligned)
        nrmse = float(np.sqrt(np.sum(np.abs(aligned - original) ** 2) / np.sum(np.abs(original) ** 2)))
        waveform_metrics[label] = nrmse
        check("waveform_nrmse_threshold:" + label, nrmse <= .01, nrmse=nrmse)
        close("reported_nrmse:" + label, row["relative_waveform_rms_error"], nrmse, atol=1e-14, rtol=0)
        close("reported_input_power:" + label, row["input_mean_power"], np.mean(np.abs(original) ** 2), atol=1e-14, rtol=0)
        close("reported_aligned_power:" + label, row["aligned_output_mean_power"], np.mean(np.abs(aligned) ** 2), atol=1e-14, rtol=0)
        check("reported_input_block_partition:" + label, sum(row["block_sizes"]) == len(x) and all(isinstance(v, int) and v > 0 for v in row["block_sizes"]))

    tone_metrics = []
    check("four_signed_tone_frequencies", [v["frequency_hz"] for v in report["tone_checks"]] == [50000, -50000, 300000, -300000])
    for row in report["tone_checks"]:
        tone = row["frequency_hz"]
        x = (.7 + .2j) * np.exp((2j * np.pi * tone / rate) * np.arange(8192))
        output = shifted_sum(x, taps)
        gain = response_sum(taps, [tone], rate)[0]
        stable = slice(count - 1, len(x))
        close("tone_steady_samples:" + str(tone), output[stable], x[stable] * gain, atol=2e-12, rtol=1e-9)
        close("tone_reported_analytic_gain:" + str(tone), row["analytic_gain_real"] + 1j * row["analytic_gain_imag"], gain, atol=1e-14, rtol=0)
        measured = np.vdot(x[stable], output[stable]) / np.vdot(x[stable], x[stable])
        close("tone_reported_measured_gain:" + str(tone), row["measured_gain_real"] + 1j * row["measured_gain_imag"], measured, atol=1e-14, rtol=0)
        power_ratio = float(np.mean(np.abs(output[stable]) ** 2) / np.mean(np.abs(x[stable]) ** 2))
        close("tone_power_analytic:" + str(tone), power_ratio, abs(gain) ** 2, atol=1e-14, rtol=1e-9)
        close("tone_reported_power:" + str(tone), row["power_ratio"], power_ratio, atol=1e-14, rtol=1e-9)
        gain_db = float(20 * np.log10(abs(measured)))
        close("tone_reported_gain_db:" + str(tone), row["amplitude_gain_db"], gain_db, atol=1e-9, rtol=0)
        check("tone_pass_or_stop_threshold:" + str(tone), abs(gain_db) <= .1 if abs(tone) == 50000 else gain_db <= -50)
        tone_metrics.append({"frequency_hz": tone, "amplitude_gain_db": gain_db})

    target, interferer = arrays["qpsk_input"], arrays["interferer_input"]
    close("synthetic_interferer_source", interferer, .5 * np.exp(2j * np.pi * 300000 * np.arange(len(target)) / rate), atol=5e-14, rtol=1e-11)
    close("mixture_source_components", arrays["mixture_input"], target + interferer)
    interferer_output = shifted_sum(interferer, taps)
    close("interferer_full_convolution", arrays["interferer_output_full"], interferer_output)
    close("mixture_full_convolution", arrays["mixture_output_full"], shifted_sum(arrays["mixture_input"], taps))
    close("mixture_linear_superposition", arrays["mixture_output_full"], arrays["qpsk_output_full"] + interferer_output)
    stable = slice(count - 1, len(target))
    interference_db = float(10 * np.log10(np.mean(np.abs(interferer_output[stable]) ** 2) / np.mean(np.abs(interferer[stable]) ** 2)))
    check("interferer_stop_threshold", interference_db <= -50, gain_db=interference_db)
    close("reported_interference_gain", report["interference_check"]["component_gain_db"], interference_db, atol=1e-9, rtol=0)
    check("no_project_fir_import", "rfsig.fir" not in sys.modules)
    timing = report["host_timing"]
    check("recorded_host_timing_consistency", len(timing["seconds"]) == timing["measured_calls"] == 20 and
          timing["warmup_calls"] == 1 and all(np.isfinite(v) and v > 0 for v in timing["seconds"]))
    close("recorded_host_timing_median", timing["median_seconds"], np.median(timing["seconds"]), atol=0, rtol=0)

    verification = {
        "schema": "rfsig.p05c_fir_independent_saved_audit.v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source_export": str(EXPORT),
        "source_export_report_sha256": sha(EXPORT / "report.json"),
        "source_export_npz_sha256": sha(EXPORT / "reference.npz"),
        "audit_script_sha256": sha(Path(__file__)),
        "method": "new process; saved arrays; direct exponential sums for every positive-frequency bin; shift-and-add convolution; no project algorithm import",
        "numpy_version": np.__version__,
        "positive_response_bins_checked": len(frequency),
        "response_metrics": metrics,
        "waveform_nrmse": waveform_metrics,
        "tone_metrics": tone_metrics,
        "interferer_gain_db": interference_db,
        "board_accessed": False,
        "gui_accessed": False,
        "scope_limitations": "saved offline simulation audit; numerical grid, not continuous-frequency extremum proof; not symbol EVM or RF/hardware performance; recorded timing checked, not rerun",
        "checks": CHECKS,
        "check_count": len(CHECKS),
        "passed_count": sum(v["passed"] for v in CHECKS),
        "passed": all(v["passed"] for v in CHECKS),
    }
    (HERE / "verification.json").write_text(json.dumps(verification, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"verification": str(HERE / "verification.json"), "passed": verification["passed"],
                      "checks": len(CHECKS), "response": metrics, "waveform_nrmse": waveform_metrics,
                      "interferer_gain_db": interference_db}, ensure_ascii=False, indent=2))
    if not verification["passed"]:
        print(json.dumps([v for v in CHECKS if not v["passed"]], indent=2))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
