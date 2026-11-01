"""Independently verify prepared files with native C --check, never --run."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from rfsig.tx_package import file_hash, verify_tx_package

ROOT = Path(__file__).resolve().parents[1]


def lp(path):
    path = Path(path).resolve().as_posix()
    return "/mnt/" + path[0].lower() + path[2:]


def plot_package(package, out):
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    fs = manifest["waveforms"][0]["sample_rate_hz"]
    fig, axes = plt.subplots(3, 2, figsize=(12, 9), layout="constrained")
    for row, item in enumerate(manifest["waveforms"][2:]):
        raw = np.fromfile(package / item["raw_file"], dtype="<i2").reshape(-1, 2).astype(float) / 16
        iq = raw[:, 0] + 1j * raw[:, 1]
        shown = min(item["samples_per_symbol"] * 4, 256)
        seam = np.concatenate((iq[-shown:], iq[:shown]))
        x = np.arange(-shown, shown) / fs * 1e6
        ax = axes[row, 0]
        ax.plot(x, seam.real, label="I", lw=.9)
        ax.plot(x, seam.imag, label="Q", lw=.9)
        ax.axvline(0, color="black", ls="--", lw=.8)
        ax.set(title=item["modulation"] + " cyclic boundary", xlabel="Time from wrap (us)", ylabel="Logical DAC counts")
        ax.legend(loc="upper right", fontsize=8)
        # Full-buffer rectangular spectrum describes generated periodic samples.
        p = np.abs(np.fft.fftshift(np.fft.fft(iq))) ** 2
        p /= max(float(np.max(p)), 1.)
        freq = np.fft.fftshift(np.fft.fftfreq(iq.size, 1 / fs)) - item["offset_hz"]
        ax = axes[row, 1]
        ax.plot(freq / 1e3, 10 * np.log10(np.maximum(p, 1e-12)), lw=.7)
        support = item["baseband_support_hz"]
        for edge in support:
            ax.axvline((edge - item["offset_hz"]) / 1e3, color="orange", ls="--", lw=.9)
        half = (support[1] - support[0]) / 2
        ax.set(xlim=(-half * 2 / 1e3, half * 2 / 1e3), ylim=(-100, 3),
               title="Periodic spectrum | dashed: ideal RRC edges",
               xlabel="Frequency relative to digital carrier (kHz)", ylabel="dB relative to largest bin")
    for ax in axes.flat:
        ax.grid(alpha=.25)
    fig.suptitle(f"OFFLINE TX FILES | NOT TRANSMITTED | {manifest['profile']}\n"
                 "Digital counts are not RF dBm; ideal RRC support is not measured 99% bandwidth", fontsize=12)
    fig.savefig(out / (manifest["profile"] + "-offline.png"), dpi=130)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, action="append", required=True)
    parser.add_argument("--native-preparation", type=Path, required=True)
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    out = ROOT / "results" / ("p12-tx-file-suite-" + stamp)
    out.mkdir()
    report = dict(status="running", rf_transmitted=False, board_accessed=False,
                  native_calls="Only --check is invoked; it returns before dlopen", packages=[], native_checks=[])
    try:
        native_dir = args.native_preparation.resolve()
        native = json.loads((native_dir / "report.json").read_text(encoding="utf-8"))
        source = ROOT / "embedded/arm_tx_source/arm_tx_source.c"
        if file_hash(source) != native["source_sha256"]:
            raise ValueError("Native preparation does not match current C source")
        archive = Path(native["archive"])
        if file_hash(archive) != native["archive_sha256"]:
            raise ValueError("Native ARM archive checksum mismatch")
        host = native_dir / "host-check"
        report["native_preparation"] = str(native_dir)
        report["native_source_sha256"] = native["source_sha256"]
        report["native_host_sha256"] = file_hash(host)
        for index, directory in enumerate(args.package):
            directory = directory.resolve()
            verify = verify_tx_package(directory)
            report["packages"].append(dict(directory=str(directory), **verify))
            manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
            for item in manifest["waveforms"]:
                argv = ["wsl.exe", "-d", "Ubuntu-24.04", "--exec", lp(host), "--check",
                        lp(directory / item["raw_file"]), str(item["sample_count"]), item["raw_sha256"]]
                run = subprocess.run(argv, capture_output=True, timeout=30)
                stem = f"{index}-{item['name']}"
                (out / (stem + ".stdout.txt")).write_bytes(run.stdout)
                (out / (stem + ".stderr.txt")).write_bytes(run.stderr)
                if run.returncode or b"INPUT_CHECK_PASS" not in run.stdout or b"SHA256=" not in run.stdout:
                    raise ValueError(f"Native file check failed: {stem}; exit {run.returncode}")
                if any(marker in run.stdout for marker in (b"libiio=", b"hw_model=", b"CYCLIC_PUSH")):
                    raise ValueError("A file-only check unexpectedly reached IIO")
                report["native_checks"].append(dict(profile=manifest["profile"], name=item["name"],
                    exit_code=run.returncode, samples=item["sample_count"], sha256=item["raw_sha256"]))
            plot_package(directory, out)
        report["status"] = "all_generated_packages_and_native_C_file_checks_passed_RF_unverified"
    except Exception as error:
        report.update(status="failed", error=f"{type(error).__name__}: {error}")
    report["finished_utc"] = datetime.now(timezone.utc).isoformat()
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(dict(output=str(out), status=report["status"], checks=len(report["native_checks"]))))
    if report["status"] == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
