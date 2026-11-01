"""Decode a captured /dev/input event stream and group it into taps.

Input is the text output of `od -An -v -tx1 /tmp/tap.raw`, where each 16-byte
input_event lands on exactly one line (od prints 16 bytes per line by default):

    sec(4) usec(4)  type(2)  code(2)  value(4)      all little-endian

EV_SYN (type 0, code 0) closes a sample; a long timestamp gap closes a tap.
For each tap this reports the median ABS_X / ABS_Y, which is what the axis
mapping has to be derived from.
"""

import argparse
import statistics
import sys
from pathlib import Path

EV_SYN = 0
EV_KEY = 1
EV_ABS = 3
ABS_CODES = {0: "ABS_X", 1: "ABS_Y", 0x18: "ABS_PRESSURE"}


def parse(text):
    events = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) != 16:
            continue
        try:
            raw = bytes(int(p, 16) for p in parts)
        except ValueError:
            continue
        sec = int.from_bytes(raw[0:4], "little")
        usec = int.from_bytes(raw[4:8], "little")
        ev_type = int.from_bytes(raw[8:10], "little")
        code = int.from_bytes(raw[10:12], "little")
        value = int.from_bytes(raw[12:16], "little")
        events.append({"t": sec + usec / 1e6, "type": ev_type, "code": code, "value": value})
    return events


def group(events, gap=0.35):
    taps = []
    current = []
    last_t = None
    for event in events:
        if last_t is not None and event["t"] - last_t > gap:
            if current:
                taps.append(current)
            current = []
        current.append(event)
        last_t = event["t"]
    if current:
        taps.append(current)
    return taps


def summarize(taps):
    rows = []
    for index, tap in enumerate(taps, start=1):
        xs = [e["value"] for e in tap if e["type"] == EV_ABS and e["code"] == 0]
        ys = [e["value"] for e in tap if e["type"] == EV_ABS and e["code"] == 1]
        ps = [e["value"] for e in tap if e["type"] == EV_ABS and e["code"] == 0x18]
        keys = [(e["code"], e["value"]) for e in tap if e["type"] == EV_KEY]
        if not xs or not ys:
            continue
        rows.append({
            "tap": index,
            "samples": len(xs),
            "x_median": int(statistics.median(xs)),
            "y_median": int(statistics.median(ys)),
            "x_range": (min(xs), max(xs)),
            "y_range": (min(ys), max(ys)),
            "pressure": int(statistics.median(ps)) if ps else None,
            "keys": keys[:4],
        })
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--gap", type=float, default=0.35)
    parser.add_argument("--trace", action="store_true",
                        help="print every sample in time order (for drag tests)")
    args = parser.parse_args()

    events = parse(args.capture.read_text(encoding="utf-8", errors="replace"))
    if not events:
        print("no events parsed")
        return 1
    print(f"events: {len(events)}   span: {events[-1]['t'] - events[0]['t']:.2f} s")

    types = {}
    for event in events:
        types[(event["type"], event["code"])] = types.get((event["type"], event["code"]), 0) + 1
    print("event histogram (type, code): count")
    for (ev_type, code), count in sorted(types.items()):
        name = ABS_CODES.get(code, "") if ev_type == EV_ABS else ""
        label = {0: "EV_SYN", 1: "EV_KEY", 3: "EV_ABS"}.get(ev_type, f"type{ev_type}")
        print(f"  {label:6s} {code:#06x} {name:14s} {count}")

    if args.trace:
        # Rebuild one row per EV_SYN-delimited sample, keeping the timestamp.
        samples = []
        pending = {}
        t0 = events[0]["t"]
        for event in events:
            if event["type"] == EV_SYN:
                if pending:
                    pending["t"] = event["t"] - t0
                    samples.append(pending)
                pending = {}
            elif event["type"] == EV_ABS:
                pending[ABS_CODES.get(event["code"], event["code"])] = event["value"]
            elif event["type"] == EV_KEY and event["code"] == 330:
                pending["TOUCH"] = event["value"]
        if pending:
            pending["t"] = events[-1]["t"] - t0
            samples.append(pending)
        print(f"\nsamples: {len(samples)}  (t relative to first event)")
        print(f"  {'t(s)':>6} {'X':>6} {'Y':>6} {'P':>5} TOUCH")
        for sample in samples:
            print(f"  {sample['t']:>6.2f} {sample.get('ABS_X', -1):>6} "
                  f"{sample.get('ABS_Y', -1):>6} {sample.get('ABS_PRESSURE', -1):>5} "
                  f"{sample.get('TOUCH', '')}")
        return 0

    taps = group(events, args.gap)
    rows = summarize(taps)
    print(f"\ntaps: {len(rows)}")
    for row in rows:
        print(f"  tap {row['tap']:2d}: X={row['x_median']:5d} {row['x_range']}  "
              f"Y={row['y_median']:5d} {row['y_range']}  "
              f"P={row['pressure']}  samples={row['samples']}  keys={row['keys']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
