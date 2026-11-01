"""Judge receiver linearity from a series of amplitude-step I/Q captures.

Each capture comes from `iio_readdev cf-ad9361-lpc > seg.bin` on the board while
the transmitter runs at a known digital peak (512/256/128/64, which doubles the
amplitude each step). The tool computes time-domain power per segment, then asks
`rfsig.saturation` whether each doubling produced the required +6.0206 dB.

Segments must be given in INCREASING amplitude order, one --segment per step.

Usage:
  python experiments/p16_check_saturation.py --full-scale 2048 --positive-rail 2047 \
      --segment peak64=/tmp/rx-peak64.bin \
      --segment peak128=/tmp/rx-peak128.bin \
      --segment peak256=/tmp/rx-peak256.bin \
      --segment peak512=/tmp/rx-peak512.bin \
      --output results/p16-saturation-20261017

No board access: this only reads files that were already captured.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from rfsig.iq_io import decode_iq_dma_s16
from rfsig.saturation import analyse_steps, iq_power_stats

ROOT = Path(__file__).resolve().parents[1]


def parse_segment(text: str) -> tuple[str, Path]:
    if "=" not in text:
        raise argparse.ArgumentTypeError("--segment expects label=path")
    label, _, path = text.partition("=")
    label = label.strip()
    if not label:
        raise argparse.ArgumentTypeError("--segment label must not be empty")
    target = Path(path.strip())
    if not target.is_file():
        raise argparse.ArgumentTypeError(f"--segment path does not exist: {target}")
    return label, target


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                          # noqa: BLE001
        pass

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--segment", action="append", type=parse_segment,
                        required=True, metavar="LABEL=PATH",
                        help="one capture per amplitude step, increasing amplitude order")
    parser.add_argument("--full-scale", type=float, default=None,
                        help="ADC magnitude considered clipped; for AD9361 RX try 2048 "
                             "(12-bit sign-extended). Omit to skip endpoint statistics.")
    parser.add_argument("--channels", type=int, default=4,
                        help="interleaved channels in the DMA dump. The TLZ7xH-EVM "
                             "cf-ad9361-lpc produces 4 (I1,Q1,I2,Q2); pairing such a "
                             "dump as 2-channel silently halves the sample count and "
                             "mixes channels. Default 4; pass 2 for a 2-channel dump.")
    parser.add_argument("--positive-rail",type=float,default=None,
                        help="positive ADC endpoint; signed-12 uses 2047 with full-scale 2048")
    parser.add_argument("--i-index", type=int, default=0)
    parser.add_argument("--q-index", type=int, default=1)
    parser.add_argument("--tolerance-db", type=float, default=0.5)
    parser.add_argument("--saturated-margin-db", type=float, default=1.0)
    parser.add_argument("--output", type=Path,
                        help="evidence directory (default results/p16-saturation-<utc>)")
    args = parser.parse_args()

    segments = []
    for label, path in args.segment:
        raw = path.read_bytes()
        iq = decode_iq_dma_s16(raw, channels=args.channels,
                               i_index=args.i_index, q_index=args.q_index)
        stats = iq_power_stats(iq, full_scale=args.full_scale,positive_rail=args.positive_rail)
        words = np.frombuffer(raw, dtype="<i2")
        segments.append({
            "label": label,
            "path": str(path),
            "bytes": path.stat().st_size,
            "sample_pairs": int(iq.size),
            "mean_power": stats.mean_power,
            "rms": stats.rms,
            "peak_abs": stats.peak_abs,
            "crest_factor_db": stats.crest_factor_db,
            "endpoint_fraction": stats.endpoint_fraction,
            "endpoint_fraction_both": stats.endpoint_fraction_both,
        })
        print(f"{label:12s} pairs={stats.sample_count:8d} "
              f"power={stats.mean_power:14.3f} rms={stats.rms:10.3f} "
              f"crest={stats.crest_factor_db:6.2f} dB"
              + (f" endpoint={stats.endpoint_fraction:.4f}" if stats.endpoint_fraction is not None else ""))

    powers = [s["mean_power"] for s in segments]
    if any(p <= 0 for p in powers):
        print("\nERROR: a segment has zero power; cannot compute step gains")
        return 3

    analysis = analyse_steps(powers, args.tolerance_db, args.saturated_margin_db)

    print("\nstep analysis (each step doubles the transmit amplitude, so power x4 = +6.0206 dB)")
    for index, step in enumerate(analysis["steps"]):
        gain = step["measured_gain_db"]
        print(f"  step {index}: {step['lower_power']:.1f} -> {step['higher_power']:.1f}  "
              f"measured {gain:+.3f} dB  error {step['error_db']:+.3f} dB  {step['verdict']}")

    verdict = "LINEAR" if analysis["all_linear"] else "NON-LINEAR"
    print(f"\nverdict: {verdict}"
          + (f" (first non-linear step {analysis['first_non_linear_index']})"
             if analysis["first_non_linear_index"] is not None else ""))
    if args.full_scale is not None:
        worst = max((s["endpoint_fraction"] or 0.0) for s in segments)
        print(f"max endpoint fraction at full_scale={args.full_scale}: {worst:.4f}")

    out = args.output or ROOT / "results" / datetime.now(timezone.utc).strftime(
        "p16-saturation-%Y%m%dT%H%M%SZ")
    out.mkdir(parents=True, exist_ok=False)
    report = {
        "schema": "rfsig.saturation_check.v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "full_scale": args.full_scale,
        "positive_rail": args.positive_rail,
        "note": ("Segments must be in increasing amplitude order. A doubling of amplitude "
                 "must produce +6.0206 dB; a smaller increment means compression."),
        "segments": segments,
        "analysis": analysis,
        "verdict": "linear" if analysis["all_linear"] else "non_linear",
    }
    target = out / "saturation.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nevidence: {target}")
    return 0 if analysis["all_linear"] else 4


if __name__ == "__main__":
    sys.exit(main())
