"""Build the single re-upload bundle for the post-power-cycle board session.

Why this exists: the board's /tmp is tmpfs and is wiped on every power cycle. The
previous session needed four separate serial uploads (~3 minutes each). Rebuilding
that by hand risks shipping a wrong or duplicated waveform, which would waste a
whole bench session. This script assembles one verified bundle and records every
hash so the upload can be checked on the board with a single `sha256sum -c`.

Every hash below is copied from a manifest that already exists on disk, and is
re-verified against the actual bytes before the tar is written. Nothing here is
transcribed from memory.

Contents:
  arm/        the ARM transmit revision that works with an empty hw_serial
  waveforms/  the six waveforms the next measurements need
  SHA256SUMS  per-file checksums, consumable by BusyBox `sha256sum -c`

Offline only. Never touches a device, never transmits.
"""

import argparse
import hashlib
import json
import shutil
import subprocess
import tarfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# The ARM revision actually used for the executed transmits (source b9ba90d3,
# ELF 0a188e1e). The 13:16 delivery package carries an older ELF that refuses to
# run because this board reports an empty hw_serial.
ARM_TAR = ROOT / "results/p12-arm-tx-prepare-20261016T073925403438Z/arm-tx-source-20261016T073925403438Z.tar"
ARM_SOURCE_SHA256 = "b9ba90d3ec85359e5b584704702e80d544ffb26e1fd28c271563316d1e41dd30"
ARM_ELF_SHA256 = "0a188e1e1c0c19a165231c1d5589ff5d72adbf284d98d2bdf39cfc6a65b1163b"

# Sources are read from these manifests so the hashes are never hand-copied.
FOLLOWUP_MANIFEST = ROOT / "results/p13-followup-waveforms-20261016T094225Z/manifest.json"
DELIVERED_MANIFEST = ROOT / "results/p12-source-delivery-20261016T051524098482Z/p201-source-20261016T051524098482Z/waveforms/existing30m72/manifest.json"
AGILITY_MANIFEST = ROOT / "results/p13-agility-waveform-20261016T093417Z/manifest.json"

FOLLOWUP_TAR = ROOT / "results/p13-followup-waveforms-20261016T094225Z/followup-waveforms.tar"
DELIVERED_TAR = ROOT / "results/p13-waveform-bundle-20261016/waveforms-existing30m72.tar"
AGILITY_TAR = ROOT / "results/p13-agility-bundle-20261016/agility.tar"

TX_LO_HZ = 2_450_000_000

# output name -> (tar, member prefix, manifest, manifest waveform name, offset_hz, note)
PLAN = (
    ("tone-positive.iq16le", DELIVERED_TAR, "existing30m72", DELIVERED_MANIFEST, "tone-positive",
     960_000, "used for the executed +960 kHz transmits; keep for repeatability"),
    ("tone-negative.iq16le", DELIVERED_TAR, "existing30m72", DELIVERED_MANIFEST, "tone-negative",
     -960_000, "negative offset: proves the digital offset sign is not swapped"),
    ("tone-double-offset.iq16le", AGILITY_TAR, "agility", AGILITY_MANIFEST, "tone-double-offset",
     1_920_000, "used for the executed +1.92 MHz transmit"),
    ("bpsk.iq16le", FOLLOWUP_TAR, "bundle", FOLLOWUP_MANIFEST, "bpsk",
     960_000, "RRC beta=0.35 shaped; for the real-data classification set"),
    ("qpsk.iq16le", FOLLOWUP_TAR, "bundle", FOLLOWUP_MANIFEST, "qpsk",
     960_000, "RRC beta=0.35 shaped"),
    ("qam16.iq16le", FOLLOWUP_TAR, "bundle", FOLLOWUP_MANIFEST, "qam16",
     960_000, "RRC beta=0.35 shaped"),
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def manifest_hashes(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {w["name"]: w["raw_sha256"] for w in data["waveforms"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    out = args.output or ROOT / "results" / datetime.now(timezone.utc).strftime("p13-upload-bundle-%Y%m%dT%H%M%SZ")
    out.mkdir(parents=True, exist_ok=False)
    stage = out / "stage"
    (stage / "arm").mkdir(parents=True)
    (stage / "waveforms").mkdir()

    report = {
        "schema": "rfsig.upload_bundle.v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "tx_lo_hz": TX_LO_HZ,
        "purpose": "single re-upload after a board power cycle; /tmp is tmpfs and is wiped",
        "goal_this_round": "photograph a marker sitting on the transmit peak, to finalise frequency and power",
        "device_accessed": False,
        "rf_transmitted": False,
    }

    # --- ARM program -------------------------------------------------------
    with tarfile.open(ARM_TAR) as tar:
        members = {m.name: m for m in tar.getmembers() if m.isfile()}
        prefix = next(iter(members)).split("/")[0]
        for member, key, expected in (
            ("arm_tx_source.c", "source", ARM_SOURCE_SHA256),
            ("bin/arm-tx-source", "elf", ARM_ELF_SHA256),
        ):
            data = tar.extractfile(members[f"{prefix}/{member}"]).read()
            digest = sha256_bytes(data)
            if digest != expected:
                raise RuntimeError(f"ARM {member}: sha256 {digest} != expected {expected}")
            name = Path(member).name
            (stage / "arm" / name).write_bytes(data)
            report[f"arm_{key}_sha256"] = digest
            report[f"arm_{key}_file"] = f"arm/{name}"
    (stage / "arm" / "arm-tx-source").chmod(0o755)

    # --- waveforms, hashes taken from manifests then re-verified ------------
    manifests = {p: manifest_hashes(p) for p in {DELIVERED_MANIFEST, FOLLOWUP_MANIFEST, AGILITY_MANIFEST}}
    report["waveforms"] = []
    for name, tar_path, prefix, manifest_path, key, offset_hz, note in PLAN:
        expected = manifests[manifest_path][key]
        with tarfile.open(tar_path) as tar:
            data = tar.extractfile(f"{prefix}/{key}.iq16le").read()
        digest = sha256_bytes(data)
        if digest != expected:
            raise RuntimeError(f"{name}: sha256 {digest} != manifest {expected}")
        if len(data) != 524_288:
            raise RuntimeError(f"{name}: unexpected size {len(data)}, expected 524288")
        (stage / "waveforms" / name).write_bytes(data)
        report["waveforms"].append({
            "file": f"waveforms/{name}",
            "bytes": len(data),
            "sha256": digest,
            "offset_hz": offset_hz,
            "expected_peak_hz": TX_LO_HZ + offset_hz,
            "note": note,
        })

    # --- checksum list consumable by BusyBox sha256sum -c ------------------
    # Line endings MUST be LF. BusyBox sha256sum does not strip a trailing CR,
    # so a CRLF file makes it look for "arm/arm-tx-source\r" and every entry
    # fails with "No such file or directory". The first build of this bundle
    # shipped CRLF and was rejected on the board; the bytes are therefore
    # written explicitly and CR presence is asserted below.
    entries = []
    for path in sorted(p for p in stage.rglob("*") if p.is_file()):
        rel = path.relative_to(stage).as_posix()
        entries.append(f"{sha256_bytes(path.read_bytes())}  {rel}")
    sums_bytes = ("\n".join(entries) + "\n").encode("utf-8")
    if b"\r" in sums_bytes:
        raise RuntimeError("SHA256SUMS must not contain CR bytes")
    if sums_bytes.count(b"\n") != len(entries) or not sums_bytes.endswith(b"\n"):
        raise RuntimeError("SHA256SUMS line count does not match the entry count")
    (stage / "SHA256SUMS").write_bytes(sums_bytes)
    report["sha256sums_entries"] = len(entries)
    report["sha256sums_bytes"] = len(sums_bytes)
    report["sha256sums_line_endings"] = "LF, CR-free, asserted at build time"

    bundle = out / "board-session-bundle.tar"
    subprocess.run(["tar", "-cf", str(bundle), "-C", str(out), "stage"], check=True)
    blob = bundle.read_bytes()
    report["bundle"] = str(bundle)
    report["bundle_bytes"] = len(blob)
    report["bundle_sha256"] = sha256_bytes(blob)
    report["uploader_limit_bytes"] = 4_194_304
    report["bundle_within_uploader_limit"] = len(blob) <= 4_194_304

    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    shutil.rmtree(stage)

    print(json.dumps({k: v for k, v in report.items() if k != "waveforms"}, ensure_ascii=False, indent=2))
    print("\nwaveforms (all hashes re-verified against disk bytes):")
    for w in report["waveforms"]:
        print(f"  {w['file']:34s} {w['sha256'][:16]}  offset {w['offset_hz']:>9}  peak {w['expected_peak_hz']}")


if __name__ == "__main__":
    main()
