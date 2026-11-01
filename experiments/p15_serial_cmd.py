"""Run read-only shell commands over serial and capture their output.

Written for BusyBox sh on a freshly booted TLZ7xH-EVM: the console drops
straight to a root prompt, so no login handshake is needed. Every command is
echoed with a unique marker on both sides so partial or interleaved output can
be detected rather than silently trusted.

Nothing here writes to the board: the caller only passes inspection commands.
"""

import argparse
import json
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import serial

ROOT = Path(__file__).resolve().parents[1]


def drain(port, seconds, quiet_after=None):
    """Read until `seconds` elapse, or until no data for `quiet_after` seconds."""
    deadline = time.time() + seconds
    chunks = []
    last_rx = time.time()
    while time.time() < deadline:
        waiting = port.in_waiting
        if waiting:
            chunks.append(port.read(waiting))
            last_rx = time.time()
        else:
            if quiet_after is not None and chunks and (time.time() - last_rx) > quiet_after:
                break
            time.sleep(0.04)
    return b"".join(chunks)


def run_command(port, command, timeout, token):
    """Send one command and return its output between the markers.

    The tty echoes whatever is typed, so a naive `echo BEGIN; cmd; echo END`
    makes the markers appear in the echo as well and the regex matches the
    echoed line instead of the real output. Splitting each marker literal with
    an empty-quote pair keeps the emitted text identical while the echoed text
    reads `__BE""GIN_...`, which cannot match. This is the whole trick.
    """
    start = f"__BEGIN_{token}__"
    end = f"__END_{token}__"
    line = (f'echo "__BE""GIN_{token}__"; {command}; '
            f'echo "__E""ND_{token}__"\r')
    port.reset_input_buffer()
    port.write(line.encode("ascii"))
    port.flush()

    buffer = b""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if port.in_waiting:
            buffer += port.read(port.in_waiting)
            if end.encode() in buffer:
                break
        else:
            time.sleep(0.04)

    text = buffer.decode("utf-8", "replace").replace("\r", "")
    match = re.search(re.escape(start) + r"\n?(.*?)" + re.escape(end), text, re.S)
    if not match:
        return {"command": command, "ok": False, "raw": text.strip()[-600:]}
    body = match.group(1)
    return {"command": command, "ok": True, "output": body.strip()}


def main():
    # The board echoes bytes that may not be valid in the Windows console
    # codepage (GBK here), which kills the run after the command was already
    # sent. Force UTF-8 with replacement so reporting can never abort a probe.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                          # noqa: BLE001
        pass

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="COM9")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--timeout", type=float, default=12.0)
    parser.add_argument("--evidence", help="directory to write the JSON transcript into")
    parser.add_argument("commands", nargs="+")
    args = parser.parse_args()

    results = []
    try:
        port = serial.Serial(args.port, args.baud, timeout=0.2)
    except Exception as exc:                                   # noqa: BLE001
        print(f"FAILED to open {args.port}: {exc}")
        return 2

    try:
        drain(port, 0.6)
        token = uuid.uuid4().hex[:12]
        for command in args.commands:
            result = run_command(port, command, args.timeout, token)
            results.append(result)
            print(f"\n$ {command}")
            if result["ok"]:
                print(result["output"] if result["output"] else "  <no output>")
            else:
                print("  !! marker not found; raw tail:")
                print("  " + (result["raw"].replace("\n", "\n  ")))
    finally:
        port.close()

    if args.evidence:
        out = Path(args.evidence)
        out.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema": "rfsig.serial_transcript.v1",
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "port": args.port,
            "baud": args.baud,
            "results": results,
        }
        target = out / "transcript.json"
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"\ntranscript: {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
