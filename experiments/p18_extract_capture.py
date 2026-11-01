"""Recover a captured I/Q segment from a serial transcript and characterise it.

The board has no network path, so the capture travels back the same way it went
out: as base64 printed to the console and stored in `transcript.json` by
`experiments/p15_serial_read.py`. This script pulls that payload out again,
verifies it against the sha256 that was computed ON THE BOARD, decodes the
4-channel CF-AD9361 layout, and reports format statistics.

Verifying against an on-board sha256 is the point: without it a truncated or
line-wrapped console read would silently look like valid data.

Usage:
  python experiments/p18_extract_capture.py \
      --transcript results/p18-capture-transfer-20261017/transcript.json \
      --expect-sha256 4b2e3d12... --channels 4 --output results/p18-capture-decoded
"""

import argparse
import base64
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from rfsig.iq_io import decode_iq_dma_s16
from rfsig.saturation import iq_power_stats

ROOT = Path(__file__).resolve().parents[1]
BASE64_SYMBOLS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=")


def extract_payload(transcript: dict, command_prefix: str) -> str:
    """Return the base64 blob produced by the command that starts with prefix."""
    for entry in transcript.get("results", []):
        command = entry.get("command", "")
        if not command.startswith(command_prefix):
            continue
        if not entry.get("ok"):
            raise RuntimeError(f"command not ok: {command}")
        body = entry.get("output", "")
        # Keep only lines that look like pure base64, so prompt echoes and
        # status lines cannot corrupt the payload.
        chunks = []
        for line in body.splitlines():
            stripped = line.strip()
            if stripped and set(stripped) <= BASE64_SYMBOLS and len(stripped) >= 4:
                chunks.append(stripped)
        if not chunks:
            raise RuntimeError("no base64-looking lines in the command output")
        return "".join(chunks)
    raise RuntimeError(f"command starting with {command_prefix!r} not found in transcript")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                          # noqa: BLE001
        pass

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transcript", required=True, type=Path)
    parser.add_argument("--command-prefix", default="base64")
    parser.add_argument("--expect-sha256", required=True)
    parser.add_argument("--channels", type=int, default=4)
    parser.add_argument("--i-index", type=int, default=0)
    parser.add_argument("--q-index", type=int, default=1)
    parser.add_argument("--full-scale", type=float, default=2048.0,
                        help="12-bit ADC magnitude treated as the rail")
    parser.add_argument("--positive-rail",type=float,default=None)
    parser.add_argument("--signal-context",choices=("unknown","no-source","known-source"),
                        default="unknown",help="record actual experiment context; do not infer it from bytes")
    parser.add_argument("--buffer-samples",type=int,default=None)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    transcript = json.loads(args.transcript.read_text(encoding="utf-8-sig"))
    blob = extract_payload(transcript, args.command_prefix)
    try:
        raw = base64.b64decode(blob, validate=True)
    except Exception as exc:                                   # noqa: BLE001
        print(f"FAILED to base64-decode payload: {exc}")
        return 2

    digest = hashlib.sha256(raw).hexdigest()
    print(f"payload bytes : {len(raw):,}")
    print(f"sha256 actual : {digest}")
    print(f"sha256 expect : {args.expect_sha256}")
    if digest != args.expect_sha256:
        print("MISMATCH - the console read was truncated or corrupted")
        return 3
    print("sha256 MATCH - payload is byte-identical to what the board computed")

    iq = decode_iq_dma_s16(raw, channels=args.channels,
                           i_index=args.i_index, q_index=args.q_index)
    stats = iq_power_stats(iq, full_scale=args.full_scale,positive_rail=args.positive_rail)

    raw_min = int(np.min(np.frombuffer(raw, dtype="<i2")))
    raw_max = int(np.max(np.frombuffer(raw, dtype="<i2")))

    print()
    print(f"channels      : {args.channels}  (I=ch{args.i_index}, Q=ch{args.q_index})")
    print(f"frames        : {iq.size:,}   ({len(raw) // (args.channels * 2):,} expected)")
    print(f"raw word range: min {raw_min}, max {raw_max}")
    print(f"mean power    : {stats.mean_power:.1f}")
    print(f"rms           : {stats.rms:.2f}")
    print(f"peak abs      : {stats.peak_abs:.0f}")
    print(f"crest factor  : {stats.crest_factor_db:.2f} dB")
    print(f"endpoint frac : {stats.endpoint_fraction}  (full_scale={args.full_scale})")

    out = args.output or ROOT / "results" / datetime.now(timezone.utc).strftime(
        "p18-capture-decoded-%Y%m%dT%H%M%SZ")
    out.mkdir(parents=True, exist_ok=False)
    (out / "segment.bin").write_bytes(raw)
    report = {
        "schema": "rfsig.capture_characterisation.v2",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source_transcript": str(args.transcript),
        "bytes": len(raw),
        "sha256": digest,
        "sha256_matches_board": True,
        "channels": args.channels,
        "i_index": args.i_index,
        "q_index": args.q_index,
        "frames": int(iq.size),
        "raw_word_min": raw_min,
        "raw_word_max": raw_max,
        "full_scale": args.full_scale,
        "positive_rail": args.positive_rail,
        "signal_context": args.signal_context,
        "dma_buffer_samples": args.buffer_samples,
        "adc_time_continuity": "unverified; file length and transport hash do not prove continuity",
        "mean_power": stats.mean_power,
        "rms": stats.rms,
        "peak_abs": stats.peak_abs,
        "crest_factor_db": stats.crest_factor_db,
        "endpoint_fraction": stats.endpoint_fraction,
        "note": ("Format statistics and byte integrity only. Signal context is explicitly supplied; "
                 "spectral identity, target reception and ADC-time continuity require separate evidence."),
    }
    target = out / "characterisation.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nevidence: {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
