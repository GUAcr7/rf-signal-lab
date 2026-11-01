"""Recompute constellation features on the continuous captures, with valid alignment.

Why a new script: the earlier feature runs aligned the constellation by stripping
the modulation with the M-th power, which is only valid for constant-modulus PSK.
On 16QAM that leaves an arbitrary rotation, and because nearest-point decisions
then fail, the measured EVM depended on luck: two captures of the same signal
scored -10.9 and -37.3 dB. ``align_rotation`` searches the rotation instead and
works for any square constellation.

Everything else is unchanged: moment-FFT carrier estimate, max-power symbol
timing, RRC matched filter, 640-sample guard per side.
"""

import json
import sys
from pathlib import Path

import numpy as np

from rfsig.carrier_tracking import align_rotation, constellation, evm_db, track_carrier
from rfsig.iq_io import load_iq_dma_s16
from rfsig.pulse_shaping import rrc_taps

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_RATE_HZ = 30_720_000
SPS = 128
GUARD = 640
ROLLOFF, SPAN = 0.35, 10

CASES = [
    ("bpsk", 2, 180.0, "p22-transfer-20261017T131327Z"),
    ("qpsk", 4, 90.0, "p22-transfer-20261017T131922Z"),
    ("qam16", 4, 90.0, "p22-transfer-20261017T132355Z"),
]


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


def features(symbols):
    magnitudes = np.abs(symbols)
    in_phase = float(np.mean(symbols.real ** 2))
    quadrature = float(np.mean(symbols.imag ** 2))
    return {
        "quadrature_suppression_db": round(
            10 * np.log10(max(in_phase, 1e-12) / max(quadrature, 1e-12)), 3),
        "amplitude_cv": round(float(np.std(magnitudes) / max(np.mean(magnitudes), 1e-12)), 4),
    }


def analyse(path, order, symmetry):
    capture = load_iq_dma_s16(path, channels=4)
    carrier = moment_carrier(capture, order)
    n = np.arange(capture.size)
    baseband = capture * np.exp(-2j * np.pi * carrier * n / SAMPLE_RATE_HZ)
    filtered = np.convolve(baseband, rrc_taps(ROLLOFF, SPAN, SPS), mode="same")

    best_offset, best_power = 0, -np.inf
    for offset in range(SPS):
        segment = filtered[offset::SPS][16:-16]
        if segment.size < 32:
            continue
        power = float(np.mean(np.abs(segment) ** 2))
        if power > best_power:
            best_offset, best_power = offset, power

    symbols = filtered[best_offset::SPS]
    trim = int(np.ceil(GUARD / SPS))
    symbols = symbols[trim:-trim]

    table = constellation(path.parent.name and "qam16" or "qam16")
    return carrier, best_offset, symbols, table


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                          # noqa: BLE001
        pass

    results = []
    for modulation, order, symmetry, transfer in CASES:
        table = constellation(modulation)
        for case in ("big1", "big2"):
            path = ROOT / "results" / transfer / f"{case}.bin"
            capture = load_iq_dma_s16(path, channels=4)
            carrier = moment_carrier(capture, order)
            n = np.arange(capture.size)
            baseband = capture * np.exp(-2j * np.pi * carrier * n / SAMPLE_RATE_HZ)
            filtered = np.convolve(baseband, rrc_taps(ROLLOFF, SPAN, SPS), mode="same")

            best_offset, best_power = 0, -np.inf
            for offset in range(SPS):
                segment = filtered[offset::SPS][16:-16]
                if segment.size < 32:
                    continue
                power = float(np.mean(np.abs(segment) ** 2))
                if power > best_power:
                    best_offset, best_power = offset, power

            symbols = filtered[best_offset::SPS]
            trim = int(np.ceil(GUARD / SPS))
            symbols = symbols[trim:-trim]

            raw_evm = evm_db(symbols, table)
            # PSK is constant modulus, so the M-th power collapses it onto a
            # phasor and gives a MEANINGFUL axis alignment. 16QAM is not
            # constant modulus: the power method leaves an arbitrary angle, so
            # the rotation has to be searched instead. But then the axis is
            # arbitrary, and quadrature suppression is not informative for QAM
            # (it is ~0 by symmetry anyway) - amplitude CV carries that case.
            # The carrier also has to be tracked for QAM: a 35 Hz error is a
            # 26 degree ramp across this block, which 16QAM decisions cannot
            # absorb the way a global rotation can be absorbed.
            if modulation in ("bpsk", "qpsk"):
                # Constant modulus, so the M-th power collapses every symbol onto
                # one phasor. But that phasor carries the constellation's own
                # reference phase as well as the received rotation:
                #     mean(unit**M) = exp(j(M*phi + theta_ref))
                # For QPSK the points sit at 45 + k*90, so theta_ref = 180 and
                # dividing the angle by M alone leaves a 45 degree error - which
                # is exactly the bug that made QPSK report -0.15 dB. Deriving
                # theta_ref from the table instead of hardcoding it keeps this
                # correct for both.
                order_m = 2 if modulation == "bpsk" else 4
                unit = symbols / np.maximum(np.abs(symbols), 1e-12)
                moment = np.mean(unit ** order_m)
                reference = np.mean((table / np.abs(table)) ** order_m)
                phi = (np.angle(moment) - np.angle(reference)) / order_m
                angle = float(np.degrees(phi))
                aligned = symbols * np.exp(-1j * phi)
            else:
                tracked = track_carrier(symbols, table, loop_bw=0.02).corrected
                aligned, angle = align_rotation(tracked, table, symmetry_deg=symmetry)
            aligned_features = features(aligned)

            row = {
                "modulation": modulation,
                "case": case,
                "carrier_hz": round(carrier, 2),
                "timing_offset": int(best_offset),
                "symbols": int(symbols.size),
                "evm_raw_db": round(raw_evm, 3),
                "rotation_deg": round(angle, 2),
                "evm_aligned_db": round(evm_db(aligned, table), 3),
                **aligned_features,
            }
            results.append(row)
            print(f"{modulation:6s} {case}  carrier={carrier:10.2f} off={best_offset:3d} "
                  f"rot={angle:5.1f}deg  raw {raw_evm:+7.2f} -> aligned "
                  f"{row['evm_aligned_db']:+7.2f} dB  quad {row['quadrature_suppression_db']:+7.2f}  "
                  f"CV {row['amplitude_cv']:.4f}")

    summary = {}
    for modulation, _, _, _ in CASES:
        rows = [r for r in results if r["modulation"] == modulation]
        summary[modulation] = {
            "evm_aligned_db": [r["evm_aligned_db"] for r in rows],
            "quadrature_suppression_db": [r["quadrature_suppression_db"] for r in rows],
            "amplitude_cv": [r["amplitude_cv"] for r in rows],
            "rotation_deg": [r["rotation_deg"] for r in rows],
        }

    print()
    print("separability (aligned, continuous captures)")
    bpsk_quad = min(summary["bpsk"]["quadrature_suppression_db"])
    other_quad = max(summary["qpsk"]["quadrature_suppression_db"]
                     + summary["qam16"]["quadrature_suppression_db"])
    qpsk_cv = max(summary["qpsk"]["amplitude_cv"])
    qam_cv = min(summary["qam16"]["amplitude_cv"])
    print(f"  BPSK quad min {bpsk_quad:+.2f} dB  vs  others max {other_quad:+.2f} dB  "
          f"gap {bpsk_quad - other_quad:.2f} dB")
    print(f"  QPSK CV max {qpsk_cv:.4f}  vs  16QAM CV min {qam_cv:.4f}  ratio {qam_cv / qpsk_cv:.1f}x")

    out = ROOT / "results" / "p23-features-continuous"
    out.mkdir(parents=True, exist_ok=True)
    (out / "features.json").write_text(json.dumps(
        {"schema": "rfsig.features_continuous.v1",
         "note": ("aligned with align_rotation; the earlier M-th-power alignment is invalid for "
                  "16QAM because it is not constant-modulus"),
         "cases": results, "summary": summary,
         "separability": {"bpsk_quad_gap_db": round(bpsk_quad - other_quad, 2),
                          "qpsk_vs_qam16_cv_ratio": round(qam_cv / qpsk_cv, 1)}},
        ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nevidence: {out / 'features.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
