"""Generate tone waveforms at scaled digital amplitude for a relative-power test.

Why this instead of an attenuator: the user has no RF attenuator, but the same
linearity question can be answered in the digital domain. Halving the peak DAC
component halves every sample, so the emitted power must fall by exactly
20*log10(0.5) = -6.0206 dB. A step test therefore checks whether the measured
relative power tracks a KNOWN change, which is what the relative-power part of
task 2 actually requires.

The waveforms differ from tone-positive.iq16le ONLY in amplitude: same
modulation, same offset, same seed, same samples-per-symbol. That keeps this a
single-variable experiment.

Offline only. Generates files and a manifest; never touches a device.
"""

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from rfsig.tx_waveforms import make_tx_waveform, pack_tx_iq_le16

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_RATE_HZ = 30_720_000
SAMPLES_PER_SYMBOL = 128
SYMBOL_COUNT = 1024
OFFSET_HZ = 960_000.0
ROLLOFF = 0.35
SPAN_SYMBOLS = 10
SEED = 20261016
TX_LO_HZ = 2_450_000_000
REFERENCE_PEAK = 512          # the amplitude used for every earlier measurement

# amplitude -> expected level relative to the reference, computed from theory
DEFAULT_PEAKS = (512, 256, 128)
PEAKS = DEFAULT_PEAKS          # replaced by --peaks when given on the command line


def build(peak: int):
    return make_tx_waveform(
        "tone",
        sample_rate_hz=SAMPLE_RATE_HZ,
        samples_per_symbol=SAMPLES_PER_SYMBOL,
        symbol_count=SYMBOL_COUNT,
        seed=SEED,
        offset_hz=OFFSET_HZ,
        digital_peak_counts=peak,
        rolloff=ROLLOFF,
        span_symbols=SPAN_SYMBOLS,
    )


def main():
    global PEAKS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--peaks",
        default=None,
        help="comma-separated digital peak counts, e.g. 512,256,128,64 "
             "(default: 512,256,128, matching the archived measurements)",
    )
    args = parser.parse_args()

    if args.peaks:
        try:
            PEAKS = tuple(int(v) for v in args.peaks.split(","))
        except ValueError:
            raise SystemExit("--peaks must be comma-separated integers")
        if not PEAKS or any(p <= 0 for p in PEAKS):
            raise SystemExit("--peaks must all be positive")
        if REFERENCE_PEAK not in PEAKS:
            raise SystemExit(f"--peaks must include the reference peak {REFERENCE_PEAK}")

    out = args.output or ROOT / "results" / datetime.now(timezone.utc).strftime("p13-power-steps-%Y%m%dT%H%M%SZ")
    out.mkdir(parents=True, exist_ok=False)
    stage = out / "bundle"
    stage.mkdir()

    records = []
    for peak in PEAKS:
        waveform = build(peak)
        raw = pack_tx_iq_le16(waveform.iq)

        # Deterministic re-generation.
        if pack_tx_iq_le16(build(peak).iq) != raw:
            raise RuntimeError(f"peak {peak}: generation is not deterministic")

        words = np.frombuffer(raw, dtype="<i2")
        if words.size != SYMBOL_COUNT * SAMPLES_PER_SYMBOL * 2:
            raise RuntimeError(f"peak {peak}: unexpected word count")
        if np.any(words & 0x000F):
            raise RuntimeError(f"peak {peak}: low four bits must be zero")
        # Stored range for logical signed-12 left-aligned: [-32768, 32752].
        if int(words.min()) < -32768 or int(words.max()) > 32752:
            raise RuntimeError(f"peak {peak}: stored counts out of range")

        # The realised peak must equal the request exactly, otherwise the
        # nominal -6.0206 dB step would not hold.
        stored_extreme = int(max(abs(int(words.min())), abs(int(words.max()))))
        realised = (stored_extreme + 8) // 16
        if realised != peak:
            raise RuntimeError(f"peak {peak}: realised peak {realised} != requested {peak}")

        energy = float(np.sum(words.astype(np.float64) ** 2))
        name = f"tone-peak{peak}.iq16le"
        (stage / name).write_bytes(raw)
        records.append({
            "file": name,
            "digital_peak_counts": peak,
            "expected_relative_db": round(20 * np.log10(peak / REFERENCE_PEAK), 6),
            "raw_bytes": len(raw),
            "raw_sha256": hashlib.sha256(raw).hexdigest(),
            "mean_I2_Q2": energy / (len(words) // 2),
            "offset_hz": OFFSET_HZ,
            "expected_peak_hz": TX_LO_HZ + OFFSET_HZ,
        })

    # The *nominal* step is -6.0206 dB, but integer quantisation means the
    # realised step is slightly different: the generator rounds each sample
    # with rint(cos*A), and rint(2x)/2 != rint(x) in general. The measured
    # digital energy ratio is therefore the honest prediction for what the RF
    # should do, and the nominal figure is kept only for reference.
    energies = np.array([r["mean_I2_Q2"] for r in records])
    ratios_db = 10 * np.log10(energies / energies[0])
    for record, measured in zip(records, ratios_db):
        nominal = 20 * np.log10(record["digital_peak_counts"] / REFERENCE_PEAK)
        record["nominal_step_db"] = round(nominal, 6)
        record["expected_relative_db"] = round(float(measured), 6)
        record["quantisation_offset_db"] = round(float(measured) - nominal, 6)
        # Guard against a real mistake rather than the expected sub-0.01 dB wobble.
        if abs(float(measured) - nominal) > 0.05:
            raise RuntimeError(f"{record['file']}: energy ratio {measured:.4f} dB deviates "
                               f"from the nominal {nominal:.4f} dB by more than 0.05 dB")

    lines = []
    for path in sorted(p for p in stage.rglob("*") if p.is_file()):
        rel = path.relative_to(stage).as_posix()
        lines.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {rel}")
    sums = ("\n".join(lines) + "\n").encode("utf-8")
    if b"\r" in sums:
        raise RuntimeError("SHA256SUMS must not contain CR bytes")
    (stage / "SHA256SUMS").write_bytes(sums)

    bundle = out / "power-steps.tar"
    subprocess.run(["tar", "-cf", str(bundle), "-C", str(out), "bundle"], check=True)
    report = {
        "schema": "rfsig.power_step_waveforms.v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": "relative-power verification by digital amplitude steps, no attenuator available",
        "single_variable": "only digital_peak_counts differs; modulation, offset, seed, sps and rolloff are identical",
        "reference_peak_counts": REFERENCE_PEAK,
        "expected_step_db": round(20 * np.log10(256 / 512), 6),
        "waveforms": records,
        "energy_ratio_check_db": [round(float(v), 6) for v in ratios_db],
        "device_accessed": False,
        "bundle": str(bundle),
        "bundle_bytes": bundle.stat().st_size,
        "bundle_sha256": hashlib.sha256(bundle.read_bytes()).hexdigest(),
    }
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    import shutil
    shutil.rmtree(stage)

    print(f"{'file':22s} {'peak':>6s} {'expected dB':>12s} {'mean_I2_Q2':>14s} {'check dB':>10s}")
    for r, m in zip(records, ratios_db):
        print(f"{r['file']:22s} {r['digital_peak_counts']:6d} {r['expected_relative_db']:12.4f} "
              f"{r['mean_I2_Q2']:14.1f} {m:10.4f}")
    print(f"\nbundle {report['bundle_bytes']:,} B  sha256 {report['bundle_sha256']}")
    print(f"evidence: {out}")


if __name__ == "__main__":
    main()
