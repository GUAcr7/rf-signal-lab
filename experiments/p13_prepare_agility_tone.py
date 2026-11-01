"""Generate the second controlled-tone waveform for TX frequency-agility proof.

Purpose: the first transmit proved a peak exists near 2.45096 GHz. One peak alone
cannot distinguish "our digitally shifted tone" from "an unrelated emitter that
happens to sit there". Repeating with a different, exactly known baseband offset
and observing the peak move by exactly that offset is the evidence that the
transmitted frequency is under our control.

This script is offline only: it generates bytes, a manifest and an independent
re-generation cross-check on the host. It never touches a device and never
transmits. Peak digital amplitude, format, shift and coherence rules are the same
ones the delivered existing30m72 set already uses.
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
DIGITAL_PEAK_COUNTS = 512
PROFILE = "agility30m72"


def build(offset_hz: float):
    return make_tx_waveform(
        "tone",
        sample_rate_hz=SAMPLE_RATE_HZ,
        samples_per_symbol=128,
        symbol_count=1024,
        seed=20261016,
        offset_hz=offset_hz,
        digital_peak_counts=DIGITAL_PEAK_COUNTS,
        rolloff=0.35,
        span_symbols=10,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offset-hz", type=float, default=1_920_000.0)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--name", default="tone-double-offset")
    args = parser.parse_args()

    out = args.output or ROOT / "results" / datetime.now(timezone.utc).strftime("p13-agility-waveform-%Y%m%dT%H%M%SZ")
    out.mkdir(parents=True, exist_ok=False)

    waveform = build(args.offset_hz)
    raw = pack_tx_iq_le16(waveform.iq)

    # Independent re-generation: the same specification must reproduce the exact
    # same bytes, so a future reader can re-derive this file from the manifest.
    again = build(args.offset_hz)
    if pack_tx_iq_le16(again.iq) != raw:
        raise RuntimeError("re-generation produced different bytes; generation is not deterministic")

    # Independent structural checks on the packed bytes, not on the array we built.
    words = np.frombuffer(raw, dtype="<i2")
    if words.size != SAMPLE_COUNT * 2:
        raise RuntimeError("unexpected interleaved word count")
    if np.any(words & 0x000F):
        raise RuntimeError("low four bits must be zero per the vendor DMA path")
    logical_peak = int(np.max(np.abs(words))) // 16
    if logical_peak != DIGITAL_PEAK_COUNTS:
        raise RuntimeError(f"logical peak {logical_peak} != requested {DIGITAL_PEAK_COUNTS}")

    # The tone must be bin coherent: an FFT of the stored samples should show one
    # dominant line exactly at the requested offset.
    spectrum = np.fft.fftshift(np.abs(np.fft.fft(words[0::2] + 1j * words[1::2])))
    freqs = np.fft.fftshift(np.fft.fftfreq(SAMPLE_COUNT, d=1.0 / SAMPLE_RATE_HZ))
    peak_index = int(np.argmax(spectrum))
    measured_offset = float(freqs[peak_index])
    if abs(measured_offset - args.offset_hz) > 1e-6:
        raise RuntimeError(f"tone landed at {measured_offset} Hz, not {args.offset_hz} Hz")
    other = np.sort(spectrum)[-2]
    if spectrum[peak_index] < 100 * max(other, 1.0):
        raise RuntimeError("tone is not a single dominant spectral line")

    raw_name = args.name + ".iq16le"
    (out / raw_name).write_bytes(raw)
    manifest = {
        "schema": "rfsig.tx_package.v1",
        "profile": PROFILE,
        "source_kind": "generated_tx_reference_not_rf",
        "rf_transmitted": False,
        "actual_tx_verified": False,
        "digital_units": "DAC counts, not dBm",
        "purpose": "second controlled tone at a known baseband offset, to prove the transmitted frequency follows the digital offset",
        "waveforms": [{
            "name": args.name,
            "modulation": "tone",
            "sample_rate_hz": SAMPLE_RATE_HZ,
            "sample_count": SAMPLE_COUNT,
            "offset_hz": args.offset_hz,
            "requested_dac_peak_counts": DIGITAL_PEAK_COUNTS,
            "raw_file": raw_name,
            "raw_sha256": hashlib.sha256(raw).hexdigest(),
            "raw_bytes": len(raw),
            "format": "LE int16 I,Q; signed12 logical DAC code multiplied by 16",
            "expected_peak_at_tx_lo_hz": 2_450_000_000 + args.offset_hz,
            **(waveform.reference),
        }],
        "checks": {
            "regeneration_identical": True,
            "low_four_bits_zero": True,
            "logical_peak_counts": logical_peak,
            "fft_peak_offset_hz": measured_offset,
            "fft_peak_is_dominant": True,
        },
        "limitations": [
            "digital DAC codes do not specify RF output power",
            "not a measured occupied bandwidth",
            "no device was accessed by this script",
        ],
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(out),
        "raw_file": str(out / raw_name),
        "raw_sha256": manifest["waveforms"][0]["raw_sha256"],
        "raw_bytes": len(raw),
        "offset_hz": args.offset_hz,
        "expected_peak_hz": 2_450_000_000 + args.offset_hz,
        "fft_peak_offset_hz": measured_offset,
    }, indent=2))


if __name__ == "__main__":
    main()
