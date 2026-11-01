"""Reassemble a base64 payload that was fetched in several serial reads.

A single 1.4 MB console read came back truncated (the sha256 check caught it), so
the capture is pulled in three sed line ranges instead. This stitches the chunks
back together in order and verifies the result against the sha256 the board
computed, so a partial transfer can never masquerade as data.
"""

import argparse
import base64
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE64_SYMBOLS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=")


def payload_from(transcript: Path) -> str:
    data = json.loads(transcript.read_text(encoding="utf-8-sig"))
    for entry in data.get("results", []):
        if not entry.get("ok"):
            continue
        chunks = []
        for line in entry.get("output", "").splitlines():
            stripped = line.strip()
            if stripped and set(stripped) <= BASE64_SYMBOLS and len(stripped) >= 4:
                chunks.append(stripped)
        if chunks:
            return "".join(chunks)
    raise RuntimeError(f"no base64 payload in {transcript}")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                          # noqa: BLE001
        pass

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transcript", action="append", required=True, type=Path,
                        help="chunk transcripts, in order")
    parser.add_argument("--expect-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    blob = ""
    for index, transcript in enumerate(args.transcript):
        piece = payload_from(transcript)
        print(f"  chunk {index}: {len(piece):,} base64 chars")
        blob += piece

    try:
        raw = base64.b64decode(blob, validate=True)
    except Exception as exc:                                   # noqa: BLE001
        print(f"FAILED to decode: {exc}")
        return 2

    digest = hashlib.sha256(raw).hexdigest()
    print(f"  bytes  : {len(raw):,}")
    print(f"  sha256 : {digest}")
    if digest != args.expect_sha256:
        print(f"  expected {args.expect_sha256}")
        print("MISMATCH - chunks are incomplete or out of order")
        return 3
    print("  MATCH  - reassembled payload is byte-identical to the board's file")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(raw)
    print(f"  written: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
