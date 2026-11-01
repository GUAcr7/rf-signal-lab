"""Block-wise known-modulation features, respecting recorded DMA boundaries.

EXP-HW-014 supersedes the original drift explanation below: old p21 captures
contain time gaps at 4096-sample boundaries. Sub-blocks are not independent RF
trials, and mean features alone do not validate a blind classifier.

Motivation: a single 512-symbol block analysed with one carrier estimate came out
*worse* than a 64-symbol block (+5.97 dB quadrature suppression versus +11.26 dB).
That is the signature of residual phase drift across a long block rather than of
insufficient samples: the two boards run on independent crystals, so the carrier
does not hold still for 2 ms.

So process the capture in short blocks, estimating the carrier in each one. That
both tracks the drift and yields several independent feature estimates, which is
what a separability claim actually needs - a spread, not one number.

Usage:
  python experiments/p21_block_analysis.py \
      --segment results/p21-rx-bpsk-long-decoded/segment.bin \
      --label bpsk --moment-order 2 --block-samples 8192
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from rfsig.iq_io import load_iq_dma_s16
from rfsig.pulse_shaping import rrc_taps
from rfsig.symbol_recovery import recover_snapshot
from p21_track_and_measure import moment_carrier as bounded_moment_carrier

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_RATE_HZ = 30_720_000


def moment_carrier(block, sample_rate_hz, order, search_hz=400_000.0):
    """Modulation-stripped FFT frequency estimate for one block."""
    unit = block / np.maximum(np.abs(block), 1e-12)
    moment = unit ** order
    window = np.hanning(moment.size)
    size = int(2 ** np.ceil(np.log2(moment.size * 4)))
    spectrum = np.abs(np.fft.fft(moment * window, n=size))
    freqs = np.fft.fftfreq(size, d=1.0 / sample_rate_hz)
    allowed = np.abs(freqs) <= search_hz * order
    if not allowed.any():
        raise ValueError("empty search band")
    index = int(np.argmax(np.where(allowed, spectrum, -np.inf)))
    left, centre, right = (spectrum[(index - 1) % size], spectrum[index],
                           spectrum[(index + 1) % size])
    denom = left - 2 * centre + right
    delta = 0.0 if denom == 0 else 0.5 * (left - right) / denom
    return float(freqs[index] + delta * (sample_rate_hz / size)) / order


def best_phase(baseband, samples_per_symbol, order):
    best_offset, best_score = 0, -np.inf
    for offset in range(samples_per_symbol):
        symbols = baseband[offset::samples_per_symbol]
        if symbols.size < 16:
            continue
        unit = symbols / np.maximum(np.abs(symbols), 1e-12)
        score = float(np.abs(np.mean(unit ** order)))
        if score > best_score:
            best_score, best_offset = score, offset
    return best_offset, best_score


def analyse_block(block, args, taps):
    # Search the whole span: the block arrives with the full ~1 MHz offset still
    # on it, so the de-modulated line sits at order x 1 MHz and a narrow band
    # around zero would only catch noise (that mistake produced carrier estimates
    # scattered over 33-361 kHz).
    carrier = bounded_moment_carrier(block,SAMPLE_RATE_HZ,args.moment_order,
                                     args.carrier_search_hz,args.carrier_hint_hz)
    recovered=recover_snapshot(block,SAMPLE_RATE_HZ,carrier,args.modulation,
                                args.samples_per_symbol,args.rolloff,args.span_symbols)
    symbols=recovered.symbols
    offset=recovered.timing_offset
    if symbols.size < 16:
        return None
    mags = np.abs(symbols)
    in_phase = float(np.mean(symbols.real ** 2))
    quadrature = float(np.mean(symbols.imag ** 2))
    return {
        "carrier_hz": round(carrier, 1),
        "symbols": int(symbols.size),
        "quadrature_suppression_db": round(
            10 * np.log10(max(in_phase, 1e-12) / max(quadrature, 1e-12)), 3),
        "amplitude_cv": round(float(np.std(mags) / max(np.mean(mags), 1e-12)), 4),
        "timing_offset": int(offset),
        "guard_samples_per_side":recovered.guard_samples,
    }


def summarize(values):
    array = np.asarray(values, dtype=float)
    return {
        "count": int(array.size),
        "mean": round(float(np.mean(array)), 3),
        "std": round(float(np.std(array, ddof=1)), 3) if array.size > 1 else 0.0,
        "min": round(float(np.min(array)), 3),
        "max": round(float(np.max(array)), 3),
    }


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                          # noqa: BLE001
        pass

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--segment", required=True, type=Path)
    parser.add_argument("--label", required=True)
    parser.add_argument("--modulation",required=True,choices=("bpsk","qpsk","qam16"))
    parser.add_argument("--dma-buffer-samples",required=True,type=int)
    parser.add_argument("--carrier-hint-hz",type=float,default=960000.)
    parser.add_argument("--carrier-search-hz",type=float,default=50000.)
    parser.add_argument("--channels", type=int, default=4)
    parser.add_argument("--samples-per-symbol", type=int, default=128)
    parser.add_argument("--rolloff", type=float, default=0.35)
    parser.add_argument("--span-symbols", type=int, default=10)
    parser.add_argument("--moment-order", type=int, default=2)
    parser.add_argument("--block-samples", type=int, default=4096)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if (args.block_samples<=0 or args.dma_buffer_samples<=0
            or args.dma_buffer_samples % args.block_samples):
        parser.error("block size must divide the recorded DMA buffer; never cross a boundary")
    if args.moment_order != (2 if args.modulation=="bpsk" else 4):
        parser.error("wrong moment order for supplied modulation")

    iq = load_iq_dma_s16(args.segment, channels=args.channels)
    taps = rrc_taps(args.rolloff, args.span_symbols, args.samples_per_symbol)

    blocks = []
    for start in range(0, iq.size - args.block_samples + 1, args.block_samples):
        block = iq[start:start + args.block_samples]
        result = analyse_block(block, args, taps)
        if result is not None:
            result["start_sample"] = start
            blocks.append(result)

    if len(blocks) < 2:
        print("need at least two usable blocks")
        return 2

    quad = summarize([b["quadrature_suppression_db"] for b in blocks])
    cv = summarize([b["amplitude_cv"] for b in blocks])
    carriers = summarize([b["carrier_hz"] for b in blocks])

    print(f"label        : {args.label}")
    print(f"samples      : {iq.size:,}   blocks of {args.block_samples:,} -> {len(blocks)}")
    print(f"carrier      : mean {carriers['mean']:,.0f} Hz  std {carriers['std']:,.0f}  "
          f"range [{carriers['min']:,.0f}, {carriers['max']:,.0f}]")
    print(f"quad suppr   : mean {quad['mean']:+.2f} dB  std {quad['std']:.2f}  "
          f"range [{quad['min']:+.2f}, {quad['max']:+.2f}]")
    print(f"amplitude CV : mean {cv['mean']:.4f}  std {cv['std']:.4f}  "
          f"range [{cv['min']:.4f}, {cv['max']:.4f}]")

    out = args.output or ROOT / "results" / datetime.now(timezone.utc).strftime(
        "p21-blocks-%Y%m%dT%H%M%SZ")
    out.mkdir(parents=True, exist_ok=False)
    report = {
        "schema": "rfsig.block_features.v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "label": args.label,
        "segment": str(args.segment),
        "samples": int(iq.size),
        "dma_buffer_samples":args.dma_buffer_samples,
        "modulation_supplied":args.modulation,
        "limits":"sub-blocks within one capture are not independent trials or blind classification evidence",
        "block_samples": args.block_samples,
        "moment_order": args.moment_order,
        "blocks": blocks,
        "summary": {"quadrature_suppression_db": quad, "amplitude_cv": cv,
                    "carrier_hz": carriers},
    }
    (out / "blocks.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                                     encoding="utf-8")
    print(f"\nevidence: {out / 'blocks.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
