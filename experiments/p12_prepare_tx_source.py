"""Prepare offline TX files only: no IIO, board connection or RF writes."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from rfsig.tx_package import PROFILES, link_plan_template, prepare_tx_package

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=PROFILES, default="existing30m72")
    parser.add_argument("--seed", type=int, default=20261016)
    parser.add_argument("--peak", type=int, default=512, help="Logical DAC component peak, not RF power")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    out = args.output or ROOT / "results" / ("p12-source-" + args.profile + "-" + stamp)
    _, verification = prepare_tx_package(out, args.profile, seed=args.seed, peak=args.peak)
    (out / "link-review.INCOMPLETE.json").write_text(
        json.dumps(link_plan_template(out), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(dict(directory=str(out.resolve()), verification=verification), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
