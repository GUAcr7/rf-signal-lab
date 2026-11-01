"""Generate peak-256 versions of the modulation waveforms for a linear link.

Why this exists: the archived BPSK/QPSK/16QAM waveforms were generated at a
digital peak of 512, and EXP-HW-011 measured that the two-board link compresses
at that level (the 256->512 step gained 5.199 dB instead of 6.0206 dB). Feeding
a nonlinear receiver would distort exactly the constellation the classifier is
meant to learn, so the modulated set is regenerated at peak 256.

Single variable changed: digital_peak_counts 512 -> 256. Every other generator
argument (seed, samples per symbol, symbol count, rolloff, span, offset) is
identical, so any difference in the captured signal comes from amplitude alone.

Control: the script first regenerates the peak-512 files and compares their
sha256 against the archived values. If that does not reproduce byte for byte,
the generator arguments are wrong and the script refuses to write the bundle.
"""

import argparse
import hashlib
import json
import sys
import tarfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from rfsig.tx_waveforms import make_tx_waveform, pack_tx_iq_le16

ROOT = Path(__file__).resolve().parents[1]

SAMPLE_RATE_HZ = 30_720_000
SAMPLE_COUNT = 131_072
SAMPLES_PER_SYMBOL = 128
ROLLOFF = 0.35
SPAN_SYMBOLS = 10
SEED = 20261016
TX_LO_HZ = 2_450_000_000
OFFSET_HZ = 960_000.0

REFERENCE_PEAK = 512
TARGET_PEAK = 256

# Archived peak-512 hashes from the recovery bundle's stage/SHA256SUMS.
ARCHIVED_512 = {
    "bpsk": "ceebe58f146a1cde27bc91b429e3ca26c6ecec5b1917d528d01ce75a2d652789",
    "qpsk": "fd56491f068881c5c315fc4fba41bfd165b0e3e25419d66755e66c372081cee9",
    "qam16": "85f8df7f3f5e986678df225da3f3421ecc453891284b12ca9ad67895be26efc2",
}

CASES = (
    ("bpsk", "BPSK"),
    ("qpsk", "QPSK"),
    ("qam16", "16QAM"),
)


def build(modulation: str, peak: int):
    return make_tx_waveform(
        modulation,
        sample_rate_hz=SAMPLE_RATE_HZ,
        samples_per_symbol=SAMPLES_PER_SYMBOL,
        symbol_count=SAMPLE_COUNT // SAMPLES_PER_SYMBOL,
        seed=SEED,
        offset_hz=OFFSET_HZ,
        digital_peak_counts=peak,
        rolloff=ROLLOFF,
        span_symbols=SPAN_SYMBOLS,
    )


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                          # noqa: BLE001
        pass

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    # --- control: reproduce the archived peak-512 files --------------------
    print("control: regenerating the peak-512 files to confirm the arguments")
    for name, modulation in CASES:
        raw = pack_tx_iq_le16(build(modulation, REFERENCE_PEAK).iq)
        digest = hashlib.sha256(raw).hexdigest()
        expected = ARCHIVED_512[name]
        if digest != expected:
            print(f"  {name:6s} MISMATCH")
            print(f"    generated {digest}")
            print(f"    archived  {expected}")
            print("refusing to continue: the generator arguments do not reproduce the archive")
            return 2
        print(f"  {name:6s} reproduces the archive exactly")
    print()

    # --- build the peak-256 bundle ----------------------------------------
    out = args.output or ROOT / "results" / datetime.now(timezone.utc).strftime(
        "p21-mod-waveforms-%Y%m%dT%H%M%SZ")
    out.mkdir(parents=True, exist_ok=False)
    stage = out / "bundle"
    stage.mkdir()

    records = []
    for name, modulation in CASES:
        waveform = build(modulation, TARGET_PEAK)
        raw = pack_tx_iq_le16(waveform.iq)

        # Determinism: the same arguments must produce the same bytes twice.
        if pack_tx_iq_le16(build(modulation, TARGET_PEAK).iq) != raw:
            print(f"  {name}: not deterministic")
            return 3

        target = stage / f"{name}.iq16le"
        target.write_bytes(raw)
        digest = hashlib.sha256(raw).hexdigest()

        import numpy as np
        iq = np.frombuffer(raw, dtype="<i2").astype(np.float64)
        pairs = iq[0::2] + 1j * iq[1::2]
        peak_abs = float(np.max(np.abs(pairs)))
        mean_power = float(np.mean(np.abs(pairs) ** 2))

        records.append({
            "file": f"{name}.iq16le",
            "modulation": modulation,
            "digital_peak_counts": TARGET_PEAK,
            "raw_bytes": len(raw),
            "raw_sha256": digest,
            "observed_peak_abs": peak_abs,
            "mean_I2_Q2": mean_power,
            "offset_hz": OFFSET_HZ,
            "expected_peak_hz": TX_LO_HZ + OFFSET_HZ,
        })
        print(f"  {name:6s} {len(raw):>8,} B  sha256 {digest[:16]}  "
              f"peak {peak_abs:7.1f}  mean_power {mean_power:14.1f}")

    sums = stage / "SHA256SUMS"
    # Write bytes, not text: Path.write_text translates "\n" to "\r\n" on
    # Windows, and BusyBox sha256sum -c then looks for "bpsk.iq16le\r" and
    # reports the file as missing. That exact failure cost a round trip here.
    sums.write_bytes(
        "".join(f"{r['raw_sha256']}  {r['file']}\n" for r in records).encode("utf-8")
    )

    archive = out / "mod-waveforms.tar"
    with tarfile.open(archive, "w") as tar:
        for member in sorted(stage.iterdir()):
            info = tarfile.TarInfo(f"bundle/{member.name}")
            info.size = member.stat().st_size
            info.mode = 0o666
            tar.addfile(info, BytesIO(member.read_bytes()))

    report = {
        "schema": "rfsig.mod_waveforms.v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": ("regenerate the modulation set at peak 256 because the link compresses at 512 "
                    "(EXP-HW-011)"),
        "single_variable": f"digital_peak_counts {REFERENCE_PEAK} -> {TARGET_PEAK}",
        "control": "peak-512 regeneration reproduced the archived sha256 byte for byte",
        "generator_args": {
            "sample_rate_hz": SAMPLE_RATE_HZ,
            "sample_count": SAMPLE_COUNT,
            "samples_per_symbol": SAMPLES_PER_SYMBOL,
            "symbol_count": SAMPLE_COUNT // SAMPLES_PER_SYMBOL,
            "seed": SEED,
            "offset_hz": OFFSET_HZ,
            "rolloff": ROLLOFF,
            "span_symbols": SPAN_SYMBOLS,
            "tx_lo_hz": TX_LO_HZ,
        },
        "waveforms": records,
        "archive": archive.name,
        "archive_bytes": archive.stat().st_size,
        "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
    }
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                                     encoding="utf-8")

    print()
    print(f"bundle {archive.stat().st_size:,} B  sha256 {report['archive_sha256']}")
    print(f"evidence: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
