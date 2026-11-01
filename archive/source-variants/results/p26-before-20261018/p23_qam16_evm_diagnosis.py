"""Diagnose the 7 dB disagreement on the second 16QAM capture.

My blind (decision-directed) pipeline reported -30.30 dB for big2 while the
data-aided validation reported -37.30 dB for the same bytes. Two candidate
causes: my carrier estimate is 34.6 Hz off (26 degrees of phase ramp over the
2.09 ms block, which matters for 16QAM), or the blind decisions themselves are
the weak link.

Method: rebuild the exact transmitted sample stream from the deterministic
generator at the reported source offset, push BOTH the capture and the
reference through the identical receive chain, then measure

    reference_evm_db  data-aided, one complex gain, no decisions
    evm_db            blind nearest-point decisions

on the same symbols. If the data-aided figure lands near -37 dB for both
captures, the data is fine and the earlier 7 dB gap was my measurement.
"""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

from rfsig.carrier_tracking import constellation, evm_db, reference_evm_db
from rfsig.iq_io import load_iq_dma_s16
from rfsig.pulse_shaping import rrc_taps
from rfsig.tx_waveforms import make_tx_waveform

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_RATE_HZ = 30_720_000
SPS = 128
PERIOD = 131_072
GUARD = 640
ROLLOFF, SPAN, SEED, PEAK = 0.35, 10, 20261016, 256
EXPECTED_SHA = "8b9e9c5ea82f8fc9204e5d14c454b66f7717ec474f8c11eb1fc486f696451236"

CAPTURES = [
    ("big1", "results/p22-transfer-20261017T132355Z/big1.bin", 86362, 994608.1),
    ("big2", "results/p22-transfer-20261017T132355Z/big2.bin", 93513, 994605.0),
]


def build_reference_samples():
    waveform = make_tx_waveform(
        "16QAM", sample_rate_hz=SAMPLE_RATE_HZ, samples_per_symbol=SPS,
        symbol_count=PERIOD // SPS, seed=SEED, offset_hz=960_000.0,
        digital_peak_counts=PEAK, rolloff=ROLLOFF, span_symbols=SPAN,
    )
    from rfsig.tx_waveforms import pack_tx_iq_le16
    raw = pack_tx_iq_le16(waveform.iq)
    digest = hashlib.sha256(raw).hexdigest()
    if digest != EXPECTED_SHA:
        raise SystemExit(f"reference waveform does not match the archive: {digest}")
    words = np.frombuffer(raw, dtype="<i2").astype(np.float64)
    return words[0::2] + 1j * words[1::2]


def moment_carrier(block, order):
    unit = block / np.maximum(np.abs(block), 1e-12)
    moment = unit ** order
    window = np.hanning(moment.size)
    size = int(2 ** np.ceil(np.log2(moment.size * 4)))
    spectrum = np.abs(np.fft.fft(moment * window, n=size))
    freqs = np.fft.fftfreq(size, d=1.0 / SAMPLE_RATE_HZ)
    index = int(np.argmax(spectrum))
    left, centre, right = (spectrum[(index - 1) % size], spectrum[index],
                           spectrum[(index + 1) % size])
    denom = left - 2 * centre + right
    delta = 0.0 if denom == 0 else 0.5 * (left - right) / denom
    return float(freqs[index] + delta * (SAMPLE_RATE_HZ / size)) / order


def chain(samples, carrier, offset):
    n = np.arange(samples.size)
    baseband = samples * np.exp(-2j * np.pi * carrier * n / SAMPLE_RATE_HZ)
    filtered = np.convolve(baseband, rrc_taps(ROLLOFF, SPAN, SPS), mode="same")
    symbols = filtered[offset::SPS]
    trim = int(np.ceil(GUARD / SPS))
    return symbols[trim:-trim]


def best_offset(samples, carrier):
    n = np.arange(samples.size)
    baseband = samples * np.exp(-2j * np.pi * carrier * n / SAMPLE_RATE_HZ)
    filtered = np.convolve(baseband, rrc_taps(ROLLOFF, SPAN, SPS), mode="same")
    best, best_power = 0, -np.inf
    for offset in range(SPS):
        seg = filtered[offset::SPS][32:-32]
        if seg.size < 32:
            continue
        power = float(np.mean(np.abs(seg) ** 2))
        if power > best_power:
            best, best_power = offset, power
    return best


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                          # noqa: BLE001
        pass

    reference = build_reference_samples()
    table = constellation("qam16")
    print(f"reference waveform regenerated, sha256 matches {EXPECTED_SHA[:16]}")
    print(f"period {PERIOD} samples, {reference.size} complex samples\n")

    report = []
    for name, relative, source_start, their_carrier in CAPTURES:
        path = ROOT / relative
        capture = load_iq_dma_s16(path, channels=4)
        indices = (source_start + np.arange(capture.size)) % PERIOD
        expected = reference[indices]

        mine = moment_carrier(capture, 4)
        rows = {}
        for label, carrier in (("my_carrier", mine), ("their_carrier", their_carrier)):
            offset = best_offset(capture, carrier)
            received = chain(capture, carrier, offset)
            ideal = chain(expected, carrier, offset)
            rows[label] = {
                "carrier_hz": round(carrier, 2),
                "offset": int(offset),
                "symbols": int(received.size),
                "reference_evm_db": round(reference_evm_db(received, ideal), 3),
                "blind_evm_db": round(evm_db(received, table), 3),
            }
        report.append({"capture": name, "source_start": source_start, "cases": rows})

        print(f"{name}  (source_start {source_start})")
        for label, row in rows.items():
            print(f"  {label:14s} carrier={row['carrier_hz']:10.2f} offset={row['offset']:3d} "
                  f"symbols={row['symbols']:4d}  data-aided {row['reference_evm_db']:+7.2f} dB  "
                  f"blind {row['blind_evm_db']:+7.2f} dB")
        print()

    out = ROOT / "results" / "p23-qam16-evm-diagnosis"
    out.mkdir(parents=True, exist_ok=True)
    (out / "diagnosis.json").write_text(
        json.dumps({"schema": "rfsig.qam16_evm_diagnosis.v1", "captures": report},
                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"evidence: {out / 'diagnosis.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
