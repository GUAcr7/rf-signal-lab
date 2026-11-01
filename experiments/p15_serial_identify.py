"""Identify which board is answering on a serial port, without changing anything.

The old PZSDR P201 and the new TLZ7xH-EVM could both enumerate as the same COM
number, and the two are told apart by `uname -a` (5.10.0 vs 4.9.0) and by
hostname (pzp201 vs something else). This script only reads and sends plain
read-only shell commands; it never writes files, never touches /dev, and never
reboots anything.

Usage: python p15_serial_identify.py --port COM9
"""

import argparse
import sys
import time

import serial


def drain(port, seconds):
    deadline = time.time() + seconds
    chunks = []
    while time.time() < deadline:
        waiting = port.in_waiting
        if waiting:
            chunks.append(port.read(waiting))
        else:
            time.sleep(0.05)
    return b"".join(chunks)


def send(port, text):
    port.write(text.encode("ascii"))
    port.flush()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="COM9")
    parser.add_argument("--baud", type=int, default=115200)
    args = parser.parse_args()

    print(f"opening {args.port} @ {args.baud} 8N1 (read-only probe)")
    try:
        port = serial.Serial(args.port, args.baud, timeout=0.2)
    except Exception as exc:                                   # noqa: BLE001
        print(f"FAILED to open: {exc}")
        return 2

    try:
        # 1) passive: catch a boot log if one is still scrolling
        passive = drain(port, 3.0)
        print(f"\n--- passive 3.0 s ({len(passive)} bytes) ---")
        print(passive.decode("utf-8", "replace").replace("\r", ""))

        # 2) wake the console with a bare newline
        send(port, "\r")
        wake = drain(port, 1.5)
        print(f"--- after newline ({len(wake)} bytes) ---")
        print(wake.decode("utf-8", "replace").replace("\r", ""))

        # 3) read-only identity query; one line, no shell metacharacters
        send(port, "uname -a; echo __ID_DONE__\r")
        identity = drain(port, 4.0)
        print(f"--- uname ({len(identity)} bytes) ---")
        print(identity.decode("utf-8", "replace").replace("\r", ""))
        return 0
    finally:
        port.close()
        print("\nport closed")


if __name__ == "__main__":
    sys.exit(main())
