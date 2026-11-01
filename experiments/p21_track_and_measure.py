"""Apply carrier tracking inside ONE recorded DMA snapshot.

IMPORTANT (EXP-HW-014): the original p21 long files contain discontinuities
between 4096-sample DMA buffers. They must not be filtered or tracked as one
continuous record. Buffer size is now mandatory, and multi-buffer input is
rejected. Use p22_resolve_capture_quality.py for historical gap diagnosis.

Contrast with p21_block_analysis.py, which sidestepped the drift by analysing
8 short blocks separately. Here the whole 512-symbol block is kept and the drift
is tracked by a decision-directed PLL, so the block finally has both the samples
and the phase coherence.

Reports EVM before and after tracking, plus the constellation features, so the
claim "tracking helps" is backed by numbers on real captures rather than by
theory.

Usage:
  python experiments/p21_track_and_measure.py \
      --segment results/p21-rx-bpsk-long-decoded/segment.bin \
      --label bpsk --modulation bpsk --moment-order 2
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from rfsig.carrier_tracking import constellation, evm_db, track_carrier
from rfsig.iq_io import load_iq_dma_s16
from rfsig.symbol_recovery import recover_snapshot

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_RATE_HZ = 30_720_000


def moment_carrier(block, sample_rate_hz, order, search_hz=None, hint_hz=0.0):
    """Modulation-stripped FFT frequency estimate over the whole block."""
    if search_hz is None:
        search_hz = sample_rate_hz / 2
    unit = block / np.maximum(np.abs(block), 1e-12)
    shifted = unit*np.exp(-2j*np.pi*hint_hz*np.arange(len(unit))/sample_rate_hz)
    moment = shifted ** order
    window = np.hanning(moment.size)
    size = int(2 ** np.ceil(np.log2(moment.size * 4)))
    spectrum = np.abs(np.fft.fft(moment * window, n=size))
    freqs = np.fft.fftfreq(size, d=1.0 / sample_rate_hz)
    allowed = np.abs(freqs) <= search_hz * order
    index = int(np.argmax(np.where(allowed, spectrum, -np.inf)))
    left, centre, right = (spectrum[(index - 1) % size], spectrum[index],
                           spectrum[(index + 1) % size])
    denom = left - 2 * centre + right
    delta = 0.0 if denom == 0 else 0.5 * (left - right) / denom
    return hint_hz+float(freqs[index] + delta * (sample_rate_hz / size)) / order


def best_phase(baseband, samples_per_symbol, order):
    best_offset, best_score = 0, -np.inf
    for offset in range(samples_per_symbol, 0, -1):
        symbols = baseband[offset - 1::samples_per_symbol]
        if symbols.size < 16:
            continue
        unit = symbols / np.maximum(np.abs(symbols), 1e-12)
        score = float(np.abs(np.mean(unit ** order)))
        if score > best_score:
            best_score, best_offset = score, offset - 1
    return best_offset, best_score


def features(symbols):
    mags = np.abs(symbols)
    in_phase = float(np.mean(symbols.real ** 2))
    quadrature = float(np.mean(symbols.imag ** 2))
    return {
        "quadrature_suppression_db": round(
            10 * np.log10(max(in_phase, 1e-12) / max(quadrature, 1e-12)), 3),
        "amplitude_cv": round(float(np.std(mags) / max(np.mean(mags), 1e-12)), 4),
    }


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                          # noqa: BLE001
        pass

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--segment", required=True, type=Path)
    parser.add_argument("--dma-buffer-samples",required=True,type=int,
                        help="recorded acquisition buffer length; never infer from file length")
    parser.add_argument("--carrier-hint-hz",type=float,default=960_000.)
    parser.add_argument("--carrier-search-hz",type=float,default=50_000.)
    parser.add_argument("--label", required=True)
    parser.add_argument("--modulation", required=True)
    parser.add_argument("--channels", type=int, default=4)
    parser.add_argument("--samples-per-symbol", type=int, default=128)
    parser.add_argument("--rolloff", type=float, default=0.35)
    parser.add_argument("--span-symbols", type=int, default=10)
    parser.add_argument("--moment-order", type=int, default=2)
    parser.add_argument("--loop-bw", type=float, default=0.02)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    iq = load_iq_dma_s16(args.segment, channels=args.channels)
    table = constellation(args.modulation)
    if args.dma_buffer_samples <= 0 or len(iq)>args.dma_buffer_samples:
        parser.error("multi-buffer input may contain time gaps; split at recorded DMA boundaries")
    expected_order=2 if len(table)==2 else 4
    if args.moment_order!=expected_order:
        parser.error("moment-order must be 2 for BPSK, 4 for QPSK/16QAM")

    carrier = moment_carrier(iq,SAMPLE_RATE_HZ,args.moment_order,
                             args.carrier_search_hz,args.carrier_hint_hz)
    recovered=recover_snapshot(iq,SAMPLE_RATE_HZ,carrier,args.modulation,
                                args.samples_per_symbol,args.rolloff,args.span_symbols)
    aligned=recovered.symbols
    symbols=aligned

    before_evm = evm_db(aligned, table)
    before_features = features(aligned)

    tracked = track_carrier(aligned, table, loop_bw=args.loop_bw)
    after_evm = evm_db(tracked.corrected, table)
    after_features = features(tracked.corrected)

    print(f"label        : {args.label}  ({args.modulation}, {symbols.size} symbols)")
    print(f"carrier      : {carrier:,.1f} Hz")
    print(f"EVM before   : {before_evm:+.2f} dB")
    print(f"EVM after    : {after_evm:+.2f} dB   improvement {before_evm - after_evm:+.2f} dB")
    print(f"quad suppr   : {before_features['quadrature_suppression_db']:+.2f} "
          f"-> {after_features['quadrature_suppression_db']:+.2f} dB")
    print(f"amplitude CV : {before_features['amplitude_cv']:.4f} "
          f"-> {after_features['amplitude_cv']:.4f}")
    print(f"converged phase: {np.degrees(tracked.phase_rad[-1]):+.2f} deg")

    out = args.output or ROOT / "results" / datetime.now(timezone.utc).strftime(
        "p21-track-%Y%m%dT%H%M%SZ")
    out.mkdir(parents=True, exist_ok=False)
    report = {
        "schema": "rfsig.carrier_tracking_measurement.v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "label": args.label,
        "modulation": args.modulation,
        "segment": str(args.segment),
        "samples": int(iq.size),
        "dma_buffer_samples":args.dma_buffer_samples,
        "time_scope":"one DMA snapshot; inter-snapshot time continuity not assumed",
        "filter_guard_samples_per_side":recovered.guard_samples,
        "timing_offset":recovered.timing_offset,
        "symbols": int(symbols.size),
        "carrier_hz": round(carrier, 1),
        "loop_bw": args.loop_bw,
        "moment_order": args.moment_order,
        "evm_before_db": round(before_evm, 3),
        "evm_after_db": round(after_evm, 3),
        "evm_improvement_db": round(before_evm - after_evm, 3),
        "features_before": before_features,
        "features_after": after_features,
        "converged_phase_deg": round(float(np.degrees(tracked.phase_rad[-1])), 3),
        "note": ("Decision-directed EVM after phase alignment, with one complex gain fit. "
                 "It is not known-symbol EVM or evidence of bit correctness. Carrier/phase "
                 "estimation uses the supplied modulation and is not a blind classifier."),
    }
    (out / "tracking.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                                       encoding="utf-8")
    print(f"\nevidence: {out / 'tracking.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
