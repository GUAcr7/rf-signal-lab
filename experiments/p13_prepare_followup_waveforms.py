"""Generate the remaining controlled-TX waveforms as one upload-ready bundle.

Covers the three follow-up measurements that need no second board:

  tone-negative  offset -960 kHz -> expected peak at 2.44904 GHz
  bpsk           offset +960 kHz, RRC beta=0.35
  qpsk           offset +960 kHz, RRC beta=0.35
  qam16          offset +960 kHz, RRC beta=0.35

The already-delivered existing30m72 set contains these same five kinds, but that
set was never carried on the board after the broadcast was wiped, and each of its
16QAM/QPSK files is 512 KiB. This bundle keeps only what the next steps need and
re-derives every file here so the bytes, manifest and independent checks live in
one place.

Offline only: generates bytes, a manifest and independent re-generation and FFT
cross-checks on the host. Never touches a device and never transmits.

Coherence rule (enforced by rfsig.tx_waveforms): the carrier must complete an
integer number of cycles per N-sample period and keep at least one FFT bin of
Nyquist margin. With N=131072 and Fs=30.72 MHz the bin is 234.375 Hz.
"""

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from rfsig.tx_waveforms import make_tx_waveform, pack_tx_iq_le16

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_RATE_HZ = 30_720_000
SAMPLE_COUNT = 131_072
SAMPLES_PER_SYMBOL = 128
DIGITAL_PEAK_COUNTS = 512
ROLLOFF = 0.35
SPAN_SYMBOLS = 10
SEED = 20261016
TX_LO_HZ = 2_450_000_000

# name, modulation, offset_hz, why this case exists
# The modulation keyword must match rfsig.tx_waveforms exactly: tone/BPSK/QPSK/16QAM.
# The output file name keeps the delivered set's lowercase convention.
CASES = (
    ("tone-negative", "tone", -960_000.0, "negative-offset tone: proves the digital offset signs are not swapped"),
    ("bpsk", "BPSK", 960_000.0, "two-phase modulation for the real-data classification set"),
    ("qpsk", "QPSK", 960_000.0, "four-phase modulation for the real-data classification set"),
    ("qam16", "16QAM", 960_000.0, "sixteen-point modulation for the real-data classification set"),
)


def build(modulation: str, offset_hz: float):
    return make_tx_waveform(
        modulation,
        sample_rate_hz=SAMPLE_RATE_HZ,
        samples_per_symbol=SAMPLES_PER_SYMBOL,
        symbol_count=SAMPLE_COUNT // SAMPLES_PER_SYMBOL,
        seed=SEED,
        offset_hz=offset_hz,
        digital_peak_counts=DIGITAL_PEAK_COUNTS,
        rolloff=ROLLOFF,
        span_symbols=SPAN_SYMBOLS,
    )


def audit(name: str, modulation: str, offset_hz: float) -> dict:
    waveform = build(modulation, offset_hz)
    raw = pack_tx_iq_le16(waveform.iq)

    # Independent re-generation: same spec must yield identical bytes.
    if pack_tx_iq_le16(build(modulation, offset_hz).iq) != raw:
        raise RuntimeError(f"{name}: generation is not deterministic")

    if len(raw) != SAMPLE_COUNT * 4:
        raise RuntimeError(f"{name}: unexpected byte length {len(raw)}")

    words = np.frombuffer(raw, dtype="<i2")
    if np.any(words & 0x000F):
        raise RuntimeError(f"{name}: low four bits must be zero for the vendor DMA path")
    # Stored int16 holds logical_code * 16, so the stored range that corresponds
    # to logical signed-12 codes [-2048, 2047] is exactly [-32768, 32752].
    # Check that range directly; do NOT use // or abs() on the stored values,
    # because floor division rounds toward minus infinity for negatives.
    if int(words.min()) < -32768 or int(words.max()) > 32752:
        raise RuntimeError(f"{name}: stored counts outside the signed-12 left-aligned range")
    stored_extreme = int(max(abs(int(words.min())), abs(int(words.max()))))
    logical_peak = (stored_extreme + 8) // 16
    if logical_peak != DIGITAL_PEAK_COUNTS:
        raise RuntimeError(f"{name}: logical peak {logical_peak} != requested {DIGITAL_PEAK_COUNTS}")

    # Validate the two components separately as integers. Do NOT build a complex
    # array here: int64 + 1j promotes to complex64 (float32), which cannot hold
    # the full int64 range exactly above 2**24 and would corrupt this very check.
    comp_i = words[0::2].astype(np.int64)
    comp_q = words[1::2].astype(np.int64)
    for label, comp in (("I", comp_i), ("Q", comp_q)):
        if int(comp.min()) < -32768 or int(comp.max()) > 32752:
            raise RuntimeError(f"{name}: {label} stored counts are not left-aligned signed-12")
        if np.any(comp % 16 != 0):
            raise RuntimeError(f"{name}: {label} values are not multiples of 16")
        logical = comp // 16
        if int(logical.min()) < -2048 or int(logical.max()) > 2047:
            raise RuntimeError(f"{name}: {label} logical codes are outside signed-12")

    # Float64 is sufficient for the FFT below (values are bounded by 32768).
    iq = comp_i.astype(np.float64) + 1j * comp_q.astype(np.float64)

    spectrum = np.fft.fftshift(np.abs(np.fft.fft(iq)))
    freqs = np.fft.fftshift(np.fft.fftfreq(SAMPLE_COUNT, d=1.0 / SAMPLE_RATE_HZ))
    magnitude = np.sort(spectrum)
    peak_index = int(np.argmax(spectrum))
    peak_hz = float(freqs[peak_index])
    peak_is_dominant = bool(spectrum[peak_index] >= 100.0 * max(magnitude[-2], 1.0))

    if modulation == "tone":
        # A pure tone must be one line, exactly on the requested offset.
        if abs(peak_hz - offset_hz) > 1e-6:
            raise RuntimeError(f"{name}: tone landed at {peak_hz} Hz, not {offset_hz} Hz")
        if not peak_is_dominant:
            raise RuntimeError(f"{name}: tone is not a single dominant spectral line")
    else:
        # A shaped carrier must be centred on the offset. The RRC spreads energy
        # around it and its finite-tap leakage is not perfectly symmetric, so the
        # power centroid is a statistical quantity, not an exact line. The
        # asymmetry grows with constellation order because the envelope excursion
        # does: measured here, BPSK < 1 kHz, QPSK 1.1 kHz, 16QAM 3.0 kHz.
        #
        # Tolerance rationale: this check exists only to catch a gross error such
        # as a DC-centred carrier or a swapped sign, not to measure frequency
        # accuracy (that is done on the instrument). Half a symbol is 120 kHz;
        # 5% of the symbol rate (12 kHz) is three times the largest asymmetry
        # observed and still far below half a symbol.
        power = spectrum ** 2
        centroid_hz = float(np.sum(freqs * power) / np.sum(power))
        tolerance_hz = 0.05 * (SAMPLE_RATE_HZ / SAMPLES_PER_SYMBOL)
        if abs(centroid_hz - offset_hz) > tolerance_hz:
            raise RuntimeError(
                f"{name}: spectral centroid {centroid_hz:.1f} Hz differs from the requested "
                f"{offset_hz:.1f} Hz by more than the {tolerance_hz:.0f} Hz sanity tolerance")

    energy = int(np.sum(iq.real ** 2 + iq.imag ** 2))
    checks = {
        "regeneration_identical": True,
        "low_four_bits_zero": True,
        "logical_peak_counts": logical_peak,
        "spectral_peak_hz": peak_hz,
        "peak_is_dominant": peak_is_dominant,
    }
    if modulation == "tone":
        checks["tone_exactly_on_requested_offset"] = abs(peak_hz - offset_hz) <= 1e-6
    else:
        checks["spectral_centroid_hz"] = centroid_hz

    return {
        "name": name,
        "modulation": modulation,
        "raw_file": name + ".iq16le",
        "raw_bytes": len(raw),
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "sample_count": SAMPLE_COUNT,
        "samples_per_symbol": SAMPLES_PER_SYMBOL if modulation != "tone" else None,
        "symbol_count": SAMPLE_COUNT // SAMPLES_PER_SYMBOL if modulation != "tone" else None,
        "symbol_rate_hz": SAMPLE_RATE_HZ / SAMPLES_PER_SYMBOL if modulation != "tone" else None,
        "offset_hz": offset_hz,
        "rrc_rolloff": ROLLOFF if modulation != "tone" else None,
        "rrc_span_symbols": SPAN_SYMBOLS if modulation != "tone" else None,
        "digital_peak_counts": DIGITAL_PEAK_COUNTS,
        "mean_I2_Q2": energy / SAMPLE_COUNT,
        "expected_peak_or_centre_hz": TX_LO_HZ + offset_hz,
        "reason": None,
        "checks": checks,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    out = args.output or ROOT / "results" / datetime.now(timezone.utc).strftime("p13-followup-waveforms-%Y%m%dT%H%M%SZ")
    out.mkdir(parents=True, exist_ok=False)
    stage = out / "bundle"
    stage.mkdir()

    records = []
    for name, modulation, offset_hz, reason in CASES:
        record = audit(name, modulation, offset_hz)
        record["reason"] = reason
        waveform = build(modulation, offset_hz)
        (stage / record["raw_file"]).write_bytes(pack_tx_iq_le16(waveform.iq))
        records.append(record)
        print(f"{name:14s} {record['raw_sha256'][:16]}  peak/centre {record['expected_peak_or_centre_hz']:.0f} Hz")

    manifest = {
        "schema": "rfsig.tx_package.v1",
        "profile": "followup30m72",
        "source_kind": "generated_tx_reference_not_rf",
        "rf_transmitted": False,
        "actual_tx_verified": False,
        "digital_units": "DAC counts, not dBm",
        "tx_lo_hz": TX_LO_HZ,
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "sample_count": SAMPLE_COUNT,
        "format": "LE int16 I,Q; signed12 logical DAC code multiplied by 16",
        "purpose": "negative-offset tone plus the three modulation classes, for the follow-up transmit and real-data measurements",
        "waveforms": records,
        "limitations": [
            "digital DAC codes do not specify RF output power",
            "theoretical RRC support is not a measured 99% occupied bandwidth",
            "cyclic repeats are not independent test frames and must not be split across train/test",
            "no device was accessed by this script",
        ],
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    bundle = out / "followup-waveforms.tar"
    import subprocess
    subprocess.run(["tar", "-cf", str(bundle), "-C", str(out), "bundle"], check=True)
    print(json.dumps({
        "output": str(out),
        "bundle": str(bundle),
        "bundle_bytes": bundle.stat().st_size,
        "bundle_sha256": hashlib.sha256(bundle.read_bytes()).hexdigest(),
        "waveforms": [r["name"] for r in records],
    }, indent=2))


if __name__ == "__main__":
    main()
