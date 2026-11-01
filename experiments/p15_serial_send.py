"""Stream a file to the Zynq console as base64 and verify it by sha256.

Why base64 + Ctrl-D rather than uudecode: this rootfs has no uudecode, only
`base64`. Feeding `base64 -d > file` on stdin and ending with a newline plus
Ctrl-D makes it see EOF and exit cleanly.

Two details that matter on this console:
  * echo is turned off first with `stty -echo`; with echo on, every byte is
    echoed back and the transfer takes roughly twice as long;
  * the tty is in canonical mode with a ~4096-byte line limit, so the encoded
    stream is broken into 76-character lines or it would be truncated.

Pacing is deliberate: no hardware flow control is in use, so writes are throttled
to roughly the line rate instead of filling the driver buffer and losing bytes.
"""

import argparse
import base64
import hashlib
import sys
import time
from pathlib import Path

import serial

LINE_WIDTH = 76
LINES_PER_WRITE = 16
TARGET_BYTES_PER_SECOND = 9_000.0


def drain(port, seconds):
    deadline = time.time() + seconds
    chunks = []
    while time.time() < deadline:
        if port.in_waiting:
            chunks.append(port.read(port.in_waiting))
        else:
            time.sleep(0.02)
    return b"".join(chunks)


def wait_for(port, needle, timeout):
    buffer = b""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if port.in_waiting:
            buffer += port.read(port.in_waiting)
            if needle in buffer:
                return True, buffer.decode("utf-8", "replace")
        else:
            time.sleep(0.02)
    return False, buffer.decode("utf-8", "replace")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                          # noqa: BLE001
        pass

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="COM9")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--remote", required=True, help="path on the board")
    args = parser.parse_args()

    data = args.source.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    encoded = base64.b64encode(data).decode("ascii")
    lines = [encoded[i:i + LINE_WIDTH] for i in range(0, len(encoded), LINE_WIDTH)]

    print(f"source      : {args.source}")
    print(f"bytes       : {len(data):,}")
    print(f"sha256      : {digest}")
    print(f"base64 lines: {len(lines):,}")
    print(f"wire bytes  : {len(encoded) + len(lines):,}")
    print(f"est. time   : {(len(encoded) + len(lines)) / TARGET_BYTES_PER_SECOND / 60:.1f} min")
    sys.stdout.flush()

    port = serial.Serial(args.port, args.baud, timeout=0.2)
    try:
        port.write(b"\x03\r")
        drain(port, 0.6)
        port.write(b"\x03\r")
        drain(port, 0.6)

        port.write(b"stty -echo\r")
        drain(port, 0.6)
        port.write(f"rm -f {args.remote}\r".encode())
        drain(port, 0.4)

        # Start the decoder and wait for its readiness banner before streaming,
        # otherwise the first chunks would be eaten by the shell as commands.
        port.write(b"echo READY_FOR_DATA; base64 -d > " + args.remote.encode() + b"\r")
        ready, banner = wait_for(port, b"READY_FOR_DATA", 6.0)
        if not ready:
            print("FAILED: decoder did not report ready")
            print(banner)
            return 3
        print("decoder started, streaming...")
        sys.stdout.flush()

        started = time.time()
        sent = 0
        for index in range(0, len(lines), LINES_PER_WRITE):
            block = "\n".join(lines[index:index + LINES_PER_WRITE]) + "\n"
            port.write(block.encode("ascii"))
            sent += len(block)
            # Drain whatever comes back so the PC-side buffer never stalls.
            if port.in_waiting:
                port.read(port.in_waiting)
            expected = sent / TARGET_BYTES_PER_SECOND
            elapsed = time.time() - started
            if expected > elapsed:
                time.sleep(expected - elapsed)
            if index % (LINES_PER_WRITE * 200) == 0 and index:
                pct = 100.0 * sent / (len(encoded) + len(lines))
                print(f"  {pct:5.1f}%  {sent:,} / {len(encoded) + len(lines):,} bytes  "
                      f"{elapsed:.0f}s")
                sys.stdout.flush()

        # EOF: newline at column 0 then Ctrl-D.
        port.write(b"\n\x04")
        ok, tail = wait_for(port, b"#", 30.0)
        print("decoder finished" if ok else "WARNING: prompt not seen after EOF")
        drain(port, 1.0)

        port.write(b"stty echo\r")
        drain(port, 0.5)
        port.write(f"sha256sum {args.remote}\r".encode())
        # Read until quiet rather than until the first newline: the first
        # newline is the echoed command, not the result.
        text = ""
        last_rx = time.time()
        deadline = time.time() + 20.0
        while time.time() < deadline:
            if port.in_waiting:
                text += port.read(port.in_waiting).decode("utf-8", "replace")
                last_rx = time.time()
            elif text and (time.time() - last_rx) > 1.2:
                break
            else:
                time.sleep(0.03)
        text = text.replace("\r", "")
        print("\n--- remote sha256sum ---")
        print(text.strip())
        if digest in text:
            print(f"\nSHA256 MATCH  {digest}")
            return 0
        print(f"\nSHA256 MISMATCH  expected {digest}")
        return 4
    finally:
        port.close()


if __name__ == "__main__":
    sys.exit(main())
