"""Disabled: the vendor RF overlay removal path caused a kernel Oops.

Original exact procedure and raw stack are retained under
results/p31-rf-driver-test-20261019T141834Z/. Candidate was NOT applied.
No force option: use a separately reviewed fresh-boot strategy after addressing
kernel/driver compatibility; never remove the current working RF overlay.
"""
import sys


def main():
    print("DISABLED: original overlay removal caused axiadc_remove NULL dereference.", file=sys.stderr)
    print("No serial port opened or hardware operation performed.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
