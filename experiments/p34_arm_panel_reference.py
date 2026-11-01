"""Reference implementation of what arm_panel computes, for cross-checking.

The board program reads interleaved int16 I/Q, applies a Hann window, runs a
radix-2 FFT, averages N frames into a power spectrum and reports the peak level,
the peak's offset in bins and the RMS of the raw samples.

This script computes exactly the same three numbers in numpy so the on-board
output can be checked against an independent implementation instead of being
taken on trust.
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
FFT_N = 1024


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                          # noqa: BLE001
        pass

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--channels", type=int, default=4)
    parser.add_argument("--frames", type=int, default=8)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    words = np.frombuffer(args.input.read_bytes(), dtype="<i2")
    if words.size % args.channels:
        raise SystemExit("file is not a whole number of frames")
    frames = words.reshape(-1, args.channels)
    pairs = frames.shape[0]
    if pairs < FFT_N * 2:
        raise SystemExit(f"need at least {FFT_N * 2} pairs, have {pairs}")

    window = 0.5 - 0.5 * np.cos(2.0 * np.pi * np.arange(FFT_N) / FFT_N)
    used = min(args.frames, pairs // FFT_N)

    acc = np.zeros(FFT_N, dtype=np.float64)
    total_power = 0.0
    for f in range(used):
        block = frames[f * FFT_N:(f + 1) * FFT_N].astype(np.float64)
        i = block[:, 0]
        q = block[:, 1]
        total_power += float(np.sum(i * i + q * q))
        spectrum = np.fft.fft(i * window + 1j * (q * window))
        acc += np.abs(spectrum) ** 2

    shifted = np.fft.fftshift(acc)
    with np.errstate(divide="ignore"):
        db = np.where(shifted > 0, 10.0 * np.log10(shifted + 1e-30), -300.0)
    peak_bin = int(np.argmax(db))
    peak = float(db[peak_bin])
    peak_offset = float(peak_bin - FFT_N // 2)
    rms = float(np.sqrt(total_power / (used * FFT_N * 2)))

    report = {
        "schema": "rfsig.arm_panel_reference.v1",
        "input": str(args.input),
        "channels": args.channels,
        "frames_used": used,
        "pairs": int(pairs),
        "peak_db": round(peak, 6),
        "peak_offset_bins": peak_offset,
        "rms_counts": round(rms, 6),
    }
    print(f"frames_used={used} pairs={pairs}")
    print(f"peak={peak:.6f} dB  peak_offset={peak_offset:+.1f} bins  rms={rms:.6f}")

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")
        print(f"evidence: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
