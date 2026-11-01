"""Offline P07 integer FIR contract, evidence and independent HDL test vectors."""

from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import sys
from time import perf_counter

import numpy as np

from rfsig.fir import apply_fir_full, design_lowpass_fir
from rfsig.fixed_fir import (
    FixedFirStream, apply_fixed_fir_full, quantize_fir_coefficients, quantize_iq_counts,
)


ROOT = Path(__file__).resolve().parents[1]
FS, CUTOFF, TAP_COUNT, COUNTS_PER_UNIT = 1_000_000, 150_000, 63, 1024
PASS_EDGE, STOP_EDGE = 100_000, 200_000
MAX_GAIN_DEVIATION_DB, MAX_RIPPLE_DB, MIN_STOP_ATTENUATION_DB = 0.1, 0.1, 50.
MAX_FIXED_VS_FLOAT_FILTERED_NRMSE = 0.001
MAX_DELAY_ALIGNED_VS_ORIGINAL_NRMSE = 0.01
SOURCES = {
    "bpsk": "p04-bpsk-20261003T102947621995Z",
    "qpsk": "p04-qpsk-20261003T103128391971Z",
    "qam16": "p04-16qam-20261003T103357180550Z",
}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def integer_oracle(counts, taps):
    """Shift-and-add integer convolution, independent of np.convolve/state API."""
    accumulators = np.zeros((len(counts)+len(taps)-1, 2), dtype=np.int64)
    values = counts.astype(np.int64)
    for index, tap in enumerate(taps):
        accumulators[index:index+len(counts)] += int(tap) * values
    rounded = np.asarray([round(Fraction(int(value), 131072))
                          for value in accumulators.flat], dtype=np.int64).reshape(-1, 2)
    saturated = (rounded < -32768) | (rounded > 32767)
    return accumulators, np.clip(rounded, -32768, 32767).astype(np.int16), saturated


def hex_file(path, values, bits):
    """One two's-complement word per line; no headers for $readmemh."""
    mask, digits = (1 << bits)-1, (bits+3)//4
    path.write_text("".join(f"{int(value)&mask:0{digits}x}\n" for value in values), encoding="ascii")
    loaded = [int(line, 16) for line in path.read_text(encoding="ascii").splitlines()]
    decoded = np.array([word-(1 << bits) if word & (1 << (bits-1)) else word
                        for word in loaded], dtype=np.int64)
    np.testing.assert_array_equal(decoded, values)
    return {"name": path.name, "bits": bits, "words": len(loaded), "sha256": sha256(path)}


def save_case(directory, name, counts, taps, float_taps=None):
    folder = directory / "vectors" / name
    folder.mkdir(parents=True)
    counts = np.asarray(counts, dtype=np.int16)
    taps = np.asarray(taps, dtype=np.int64)
    result = apply_fixed_fir_full(counts, taps)
    acc, expected, saturated = integer_oracle(counts, taps)
    np.testing.assert_array_equal(result.accumulators, acc)
    np.testing.assert_array_equal(result.counts, expected)
    np.testing.assert_array_equal(result.saturated, saturated)
    stream, pieces, start = FixedFirStream(taps), [], 0
    block_pattern = [1, 7, 2, 127, 3, 1024, 19]
    while start < len(counts):
        length = min(block_pattern[len(pieces) % len(block_pattern)], len(counts)-start)
        pieces.append(stream.process(counts[start:start+length]))
        start += length
    pieces.append(stream.finish())
    for field in ("counts", "accumulators", "saturated"):
        np.testing.assert_array_equal(np.concatenate([getattr(piece, field) for piece in pieces]),
                                      getattr(result, field))
    stream.reset()
    np.testing.assert_array_equal(stream.process(counts[:1]).counts, result.counts[:1])
    files = [hex_file(folder / "coefficients.hex", taps, 18)]
    for column, label in enumerate(("i", "q")):
        files.append(hex_file(folder / f"input_{label}.hex", counts[:, column], 12))
        files.append(hex_file(folder / f"expected_{label}.hex", expected[:, column], 16))
        # Flag words are unsigned single hexadecimal digits, not signed samples.
        path = folder / f"saturated_{label}.hex"
        path.write_text("".join(f"{int(value)}\n" for value in saturated[:, column]), encoding="ascii")
        np.testing.assert_array_equal([int(line) for line in path.read_text().splitlines()], saturated[:, column])
        files.append({"name": path.name, "bits": 1, "unsigned": True,
                      "words": len(saturated), "sha256": sha256(path)})
    metadata = {
        "name": name, "input_count": len(counts), "tap_count": len(taps),
        "tail_zero_input_count": len(taps)-1, "expected_output_count": len(expected),
        "input_columns": ["I", "Q"], "input_bits": 12, "coefficient_bits": 18,
        "coefficient_fractional_bits": 17, "accumulator_bits": 36, "output_bits": 16,
        "rounding": "nearest_ties_to_even_before_signed_16_saturation",
        "saturation_components": [int(saturated[:, c].sum()) for c in range(2)],
        "max_abs_accumulator": int(np.max(np.abs(acc))),
        "full_tail_semantics": "feed M-1 explicit all-zero I/Q samples after the listed inputs",
        "all_integer_oracle_and_stream_comparisons_exact": True, "files": files,
    }
    if float_taps is not None:
        floating = np.column_stack([np.convolve(counts[:, c].astype(float), float_taps)
                                    for c in range(2)])
        bound = float(np.max(abs(counts.astype(np.int64))) *
                      np.sum(abs(taps/131072-float_taps)) + 0.5)
        error = float(np.max(abs(expected.astype(float)-floating)))
        assert not saturated.any()
        assert error <= bound + 1e-10
        metadata["same_integer_input_float_comparison"] = {
            "per_component_max_abs_error_counts": error,
            "a_priori_bound_counts": bound,
            "bound_definition": "max_abs_input_count * sum(abs(h_quantized-h_float)) + 0.5",
            "passed": True,
        }
    (folder / "case.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return metadata, result


def main():
    started = perf_counter()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    directory = ROOT / "results" / f"p07-fixed-fir-{stamp}"
    directory.mkdir(parents=True, exist_ok=False)
    h = design_lowpass_fir(FS, CUTOFF, TAP_COUNT)
    hq = quantize_fir_coefficients(h)
    quantized_h = hq / 131072
    np.testing.assert_array_equal(hq, hq[::-1])
    frequency = np.fft.rfftfreq(262144, 1/FS)
    response = np.fft.rfft(quantized_h, 262144)
    edges = np.array([0, 84375, PASS_EDGE, CUTOFF, STOP_EDGE, FS/2])
    edge_response = np.exp(-2j*np.pi*edges[:, None]*np.arange(TAP_COUNT)/FS) @ quantized_h
    f = np.concatenate([frequency, edges])
    r = np.concatenate([response, edge_response])
    db = 20*np.log10(np.maximum(abs(r), 1e-300))
    pass_deviation = float(abs(db[f <= PASS_EDGE]).max())
    pass_ripple = float(np.ptp(db[f <= PASS_EDGE]))
    stop_attenuation = float(-db[f >= STOP_EDGE].max())
    assert pass_deviation <= MAX_GAIN_DEVIATION_DB
    assert pass_ripple <= MAX_RIPPLE_DB
    assert stop_attenuation >= MIN_STOP_ATTENUATION_DB
    cross_indices = np.unique(np.rint(np.linspace(0, len(frequency)-1, 513)).astype(int))
    direct = np.exp(-2j*np.pi*frequency[cross_indices, None]*np.arange(TAP_COUNT)/FS) @ quantized_h
    np.testing.assert_allclose(response[cross_indices], direct, atol=3e-14, rtol=1e-12)

    rng = np.random.default_rng(70704)
    n = np.arange(4096)
    cases = {
        "zero": np.zeros((64, 2), dtype=np.int16),
        "positive_impulse": np.array([[2047, 0]], dtype=np.int16),
        "negative_impulse": np.array([[0, -2048]], dtype=np.int16),
        "dc": np.tile([1024, -1024], (128, 1)).astype(np.int16),
        "near_fullscale": np.tile([[2047, -2048], [-2048, 2047]], (64, 1)).astype(np.int16),
        "random_12bit": rng.integers(-2048, 2048, size=(1024, 2), dtype=np.int16),
        "two_tones": quantize_iq_counts(.6*np.exp(2j*np.pi*50000*n/FS) +
                                        .3*np.exp(2j*np.pi*300000*n/FS)),
    }
    for tone in (50000, -50000, 300000, -300000):
        cases[f"tone_{'p' if tone > 0 else 'n'}{abs(tone)}"] = quantize_iq_counts(
            .7*np.exp(2j*np.pi*tone*n/FS))

    reports, arrays = [], {"taps_float": h, "taps_integer": hq,
                           "frequency_hz": frequency, "response_quantized": response,
                           "edge_frequency_hz": edges, "edge_response_quantized": edge_response}
    for name, counts in cases.items():
        metadata, result = save_case(directory, name, counts, hq, h)
        reports.append(metadata)
        arrays[f"{name}_input_counts"] = counts
        arrays[f"{name}_output_counts"] = result.counts
        arrays[f"{name}_accumulators"] = result.accumulators
    np.testing.assert_array_equal(arrays["dc_output_counts"][62:128],
                                  np.tile([1024, -1024], (66, 1)))

    source_hashes, waveform_reports = {}, []
    for label, source_name in SOURCES.items():
        source = ROOT / "results" / source_name
        meta = json.loads((source / "metadata.json").read_text(encoding="utf-8"))
        assert meta["source"] == "python_simulation_not_rf_capture"
        assert meta["sample_rate_hz"] == FS and meta["symbol_rate_hz"] == 125000
        assert meta["rolloff"] == 0.35
        assert sha256(source / "reference.npz") == meta["npz_sha256"]
        source_hashes[source_name] = {name: sha256(source / name)
                                     for name in ("metadata.json", "reference.npz")}
        with np.load(source / "reference.npz", allow_pickle=False) as saved:
            x = saved["shaped_iq"].copy()
        counts = quantize_iq_counts(x, COUNTS_PER_UNIT)
        metadata, result = save_case(directory, label, counts, hq, h)
        reports.append(metadata)
        reconstructed = (result.counts[:, 0].astype(float)+1j*result.counts[:, 1]) / COUNTS_PER_UNIT
        float_output = apply_fir_full(x, h)
        fixed_float_nrmse = float(np.linalg.norm(reconstructed-float_output) / np.linalg.norm(float_output))
        aligned = reconstructed[31:31+len(x)]
        aligned_nrmse = float(np.linalg.norm(aligned-x) / np.linalg.norm(x))
        assert fixed_float_nrmse <= MAX_FIXED_VS_FLOAT_FILTERED_NRMSE
        assert aligned_nrmse <= MAX_DELAY_ALIGNED_VS_ORIGINAL_NRMSE
        waveform_reports.append({
            "label": label, "source_record": source_name, "input_count": len(x),
            "scale_counts_per_simulation_unit": COUNTS_PER_UNIT,
            "input_peak_abs_component_before_scale": float(max(abs(x.real).max(), abs(x.imag).max())),
            "input_max_abs_count": int(abs(counts.astype(np.int64)).max()),
            "fixed_vs_float_filtered_nrmse": fixed_float_nrmse,
            "fixed_vs_float_filtered_nrmse_limit": MAX_FIXED_VS_FLOAT_FILTERED_NRMSE,
            "delay_aligned_vs_original_nrmse": aligned_nrmse,
            "delay_aligned_vs_original_nrmse_limit": MAX_DELAY_ALIGNED_VS_ORIGINAL_NRMSE,
            "output_saturation_components": int(result.saturated.sum()), "passed": True,
        })
        arrays[f"{label}_input_counts"] = counts
        arrays[f"{label}_output_counts"] = result.counts
        arrays[f"{label}_accumulators"] = result.accumulators

    custom = [
        ("asymmetric_hand", [[8, 16], [24, -8]], [65536, -32768, 16384]),
        ("ties_even", [[1, 3], [5, -1], [-3, -5]], [65536]),
        ("saturation_both_signs", np.tile([2047, -2048], (80, 1)), np.full(63, 131071)),
        ("accumulator_extreme", np.full((80, 2), -2048), np.full(63, -131072)),
    ]
    for name, counts, taps in custom:
        metadata, result = save_case(directory, name, counts, taps)
        reports.append(metadata)
        arrays[f"{name}_input_counts"] = np.asarray(counts, dtype=np.int16)
        arrays[f"{name}_taps_integer"] = np.asarray(taps, dtype=np.int64)
        arrays[f"{name}_output_counts"] = result.counts
        arrays[f"{name}_accumulators"] = result.accumulators
    np.testing.assert_array_equal(arrays["asymmetric_hand_output_counts"],
                                  [[4, 8], [10, -8], [-5, 4], [3, -1]])
    np.testing.assert_array_equal(arrays["ties_even_output_counts"], [[0, 2], [2, 0], [-2, -2]])
    np.savez_compressed(directory / "reference.npz", **arrays)
    with np.load(directory / "reference.npz", allow_pickle=False) as saved:
        for name, values in arrays.items():
            np.testing.assert_array_equal(saved[name], values)
    code_paths = ["src/rfsig/fixed_fir.py", "src/rfsig/fir.py", "tests/test_fixed_fir.py",
                  "experiments/p07_fixed_fir_reference.py"]
    report = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "offline_integer_reference_and_vectors_passed_not_RTL_or_hardware",
        "python": sys.version, "numpy": np.__version__, "sample_rate_hz": FS,
        "cutoff_hz": CUTOFF, "tap_count": TAP_COUNT, "delay_samples": 31,
        "delay_seconds_at_experiment_sample_rate": 31/FS,
        "contract": {"input_bits": 12, "input_units": "signed unscaled integer I/Q counts",
                     "coefficient_bits": 18, "coefficient_fractional_bits": 17,
                     "accumulator_bits": 36, "output_bits": 16,
                     "rounding": "nearest_ties_to_even", "output_overflow": "saturate_per_component_with_flag",
                     "input_or_coefficient_overflow": "reject_before_processing",
                     "accumulator_overflow": "reject_never_wrap",
                     "input_scale_for_P04_only": COUNTS_PER_UNIT,
                     "no_decimation": True},
        "worst_all_legal_63_tap_accumulator_bound": 63*2048*131072,
        "signed_36_bit_positive_limit": (1 << 35)-1,
        "coefficient_integer_sum": int(hq.sum()), "coefficient_abs_integer_sum": int(abs(hq).sum()),
        "coefficient_max_abs_error": float(abs(quantized_h-h).max()),
        "coefficient_l1_error": float(abs(quantized_h-h).sum()),
        "response": {"max_pass_gain_deviation_db": pass_deviation, "pass_ripple_db": pass_ripple,
                     "stop_attenuation_db": stop_attenuation,
                     "pass_edge_hz": PASS_EDGE, "stop_edge_hz": STOP_EDGE,
                     "max_pass_gain_deviation_db_limit": MAX_GAIN_DEVIATION_DB,
                     "pass_ripple_db_limit": MAX_RIPPLE_DB,
                     "min_stop_attenuation_db_limit": MIN_STOP_ATTENUATION_DB,
                     "frequency_grid_points": len(frequency), "passed": True},
        "waveforms": waveform_reports, "cases": reports, "case_count": len(reports),
        "source_sha256": source_hashes,
        "code_sha256": {path: sha256(ROOT / path) for path in code_paths},
        "reference_npz_sha256": sha256(directory / "reference.npz"),
        "saved_arrays_roundtrip_exact": True,
        "elapsed_experiment_seconds_not_hardware_throughput": perf_counter()-started,
        "limitations": ["Fs=1 MS/s candidate only; not 30.72 MS/s board integration",
                        "no RF access, no transmission, no firmware change",
                        "no claim of RTL simulation, synthesis, resource, timing or hardware throughput",
                        "same-I/Q component ordering requires later verification at the actual HDL insertion point",
                        "NRMSE is waveform error, not symbol EVM, BER, AI accuracy or calibrated RF performance"],
    }
    (directory / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (directory / "manifest.json").write_text(json.dumps({
        "vector_format": "separate_twos_complement_hex_files_no_headers",
        "cases": [{"name": item["name"], "directory": f"vectors/{item['name']}",
                   "input_count": item["input_count"], "tap_count": item["tap_count"],
                   "expected_output_count": item["expected_output_count"]} for item in reports],
        "protocol": "each case starts with reset; feed listed input then M-1 zero samples; compare every output and saturation flag",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"directory": str(directory), "case_count": len(reports),
                      "response": report["response"], "waveforms": waveform_reports,
                      "all_checks_passed": True}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
