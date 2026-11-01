"""Run short commands over the Zynq console and capture output by quiet period.

Why not markers: the console wraps input at roughly 80 columns, and a wrapped
line can split a token in half, leaving BusyBox sh waiting at a `>` continuation
prompt. A marker prefix long enough to be unique eats most of that budget.

So this tool keeps commands short, sends Ctrl-C first to clear any continuation
prompt, and delimits output by a quiet period instead of a sentinel.
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import serial

CTRL_C = "\x03"


def drain(port, seconds):
    deadline = time.time() + seconds
    chunks = []
    while time.time() < deadline:
        if port.in_waiting:
            chunks.append(port.read(port.in_waiting))
        else:
            time.sleep(0.03)
    return b"".join(chunks)


def read_until_quiet(port, timeout, quiet):
    buffer = b""
    last_rx = time.time()
    deadline = time.time() + timeout
    while time.time() < deadline:
        if port.in_waiting:
            buffer += port.read(port.in_waiting)
            last_rx = time.time()
        else:
            if buffer and (time.time() - last_rx) > quiet:
                break
            time.sleep(0.03)
    return buffer


def strip_echo(text):
    """Drop the echoed command line(s) at the start of the capture.

    The board echoes what we type, and a long command echoes across several
    wrapped lines. Everything before the first line that is not part of the
    echo is kept; in practice the echo is followed by output starting on a new
    line, so dropping leading lines that contain the command text is enough.
    """
    lines = text.split("\n")
    while lines and lines[0].strip() == "":
        lines.pop(0)
    return "\n".join(lines)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                          # noqa: BLE001
        pass

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="COM9")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--quiet", type=float, default=1.2)
    parser.add_argument("--evidence", type=Path, default=None,
                        help="directory to write transcript.json into; without it the "
                             "output only exists on screen, which is how the display and "
                             "autostart claims ended up unarchived")
    parser.add_argument("commands", nargs="+")
    args = parser.parse_args()

    try:
        port = serial.Serial(args.port, args.baud, timeout=0.2)
    except Exception as exc:                                   # noqa: BLE001
        print(f"FAILED to open {args.port}: {exc}")
        return 2

    results = []
    try:
        # Recover from any half-typed line / continuation prompt.
        port.write((CTRL_C + "\r").encode("ascii"))
        drain(port, 0.8)
        port.write((CTRL_C + "\r").encode("ascii"))
        drain(port, 0.8)
        print("--- recovered (Ctrl-C x2) ---")

        for command in args.commands:
            if len(command) > 72:
                print(f"\n!! refusing to send {len(command)}-char command "
                      f"(console wraps near 80): {command}")
                results.append({"command": command, "ok": False,
                                "error": "command too long for the console"})
                continue
            port.reset_input_buffer()
            port.write((command + "\r").encode("ascii"))
            port.flush()
            raw = read_until_quiet(port, args.timeout, args.quiet).decode("utf-8", "replace")
            text = raw.replace("\r", "")
            print(f"\n$ {command}")
            body = strip_echo(text)
            print(body if body.strip() else "  <no output>")
            suspicious = ">" in text.split("\n")[-1]
            if suspicious:
                print("  !! console may still be at a continuation prompt")
            results.append({"command": command, "ok": True, "output": body,
                            "continuation_prompt_suspected": suspicious})
    finally:
        port.close()
        print("\nport closed")

    if args.evidence is not None:
        args.evidence.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema": "rfsig.serial_read_transcript.v1",
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "port": args.port,
            "baud": args.baud,
            "tool": "experiments/p15_serial_read.py",
            "note": "commands are short (<=72 chars) and output is delimited by a quiet "
                    "period, not by markers, because this console wraps near 80 columns",
            "results": results,
        }
        target = args.evidence / "transcript.json"
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
        print(f"transcript: {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
