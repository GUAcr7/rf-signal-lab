"""Prepare/check source artifacts or inspect IIO; never starts RF from the PC.

The separately built ARM binary owns a finite cyclic session when a conducted
link has been reviewed. Printed commands are proposals, not executed actions.
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from rfsig.iio_runtime import parse_iio_gain_db, use_libiio
from rfsig.rf_link_budget import validate_link_plan
from rfsig.tx_package import file_hash, verify_tx_package

ROOT = Path(__file__).resolve().parents[1]
DLL_DIR = Path(r"D:\FPGA natch\IIO-Oscilloscope-v0.18-portable\app\bin")


def _channel_value(device, channel, output, attribute):
    ch = device.find_channel(channel, output)
    if ch is None or attribute not in ch.attrs:
        raise ValueError(f"Missing {channel}/{attribute}")
    return ch.attrs[attribute].value


def inspect_context(ctx):
    """Only reads attributes and scan descriptions; no enables, buffers or writes."""
    devices = []
    for device in ctx.devices:
        scan = []
        for channel in device.channels:
            if not channel.scan_element:
                continue
            f = channel.data_format
            scan.append(dict(id=channel.id, output=channel.output, bits=f.bits,
                             storage_bits=f.length, shift=f.shift, signed=f.is_signed,
                             big_endian=f.is_be, repeat=f.repeat))
        devices.append(dict(id=device.id, name=device.name, scan_channels=scan))
    phy = ctx.find_device("ad9361-phy")
    dac = ctx.find_device("cf-ad9361-dds-core-lpc")
    if phy is None or dac is None:
        raise ValueError("Expected AD9361 PHY and TX interface are not visible")
    # No writes occur even if the device is another board; the later run gate pins P201.
    settings = dict(
        board_model=ctx.attrs.get("hw_model"), hardware_serial=ctx.attrs.get("hw_serial"),
        guard_identity=ctx.attrs.get("hw_serial") or None,
        identity_kind="hardware_serial" if ctx.attrs.get("hw_serial") else None,
        sample_rate_hz=int(_channel_value(phy, "voltage0", True, "sampling_frequency")),
        tx_dma_sample_rate_hz=int(_channel_value(dac, "voltage0", True, "sampling_frequency")),
        tx_lo_hz=int(_channel_value(phy, "altvoltage1", True, "frequency")),
        tx_rf_bandwidth_hz=int(_channel_value(phy, "voltage0", True, "rf_bandwidth")),
        tx_hardwaregain_db=parse_iio_gain_db(_channel_value(phy, "voltage0", True, "hardwaregain")),
        tx_rf_port=_channel_value(phy, "voltage0", True, "rf_port_select"))
    modes = {key: phy.debug_attrs[key].value for key in ("bist_tone", "bist_prbs", "loopback")}
    dds = {ch.id: {key: ch.attrs[key].value for key in ("raw", "scale") if key in ch.attrs}
           for ch in dac.channels if ch.output and ch.id.startswith("altvoltage")}
    return dict(schema="rfsig.iio_source_snapshot.v1", read_only=True, rf_transmitted=False,
                context_attrs=dict(ctx.attrs), iio_server_version=list(ctx.version), devices=devices,
                tx=settings, bist_modes=modes, dds=dds,
                rx=dict(sample_rate_hz=int(_channel_value(phy, "voltage0", False, "sampling_frequency")),
                        rx_lo_hz=int(_channel_value(phy, "altvoltage0", True, "frequency")),
                        rx_rf_bandwidth_hz=int(_channel_value(phy, "voltage0", False, "rf_bandwidth")),
                        rx_rf_port=_channel_value(phy, "voltage0", False, "rf_port_select")))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    verify = sub.add_parser("verify", help="Offline hashes, byte format and tone FFT")
    verify.add_argument("package", type=Path)
    inspect = sub.add_parser("inspect", help="Read-only IIO status, no buffers or writes")
    inspect.add_argument("--uri", default="ip:192.168.2.1")
    inspect.add_argument("--libiio-dir", type=Path, default=DLL_DIR)
    inspect.add_argument("--output", type=Path)
    review = sub.add_parser("review", help="Review offline evidence and propose a bounded ARM command")
    review.add_argument("package", type=Path)
    review.add_argument("plan", type=Path)
    review.add_argument("snapshot", type=Path)
    args = parser.parse_args()
    if args.action == "verify":
        print(json.dumps(verify_tx_package(args.package), ensure_ascii=False, indent=2))
        return
    if args.action == "review":
        verify_tx_package(args.package)
        manifest = json.loads((args.package / "manifest.json").read_text(encoding="utf-8"))
        plan = json.loads(args.plan.read_text(encoding="utf-8-sig"))
        snapshot = json.loads(args.snapshot.read_text(encoding="utf-8-sig"))
        if snapshot.get("schema") != "rfsig.iio_source_snapshot.v1" or snapshot.get("status") != "readonly_inspection_passed":
            raise ValueError("A successful actual IIO source inspection is required")
        wave = next((w for w in manifest["waveforms"] if w["name"] == plan.get("waveform_name")), None)
        if wave is None:
            raise ValueError("Reviewed waveform is not in this package")
        result = validate_link_plan(plan, package_sha256=file_hash(args.package / "manifest.json"),
                                    waveform=wave, current_tx=snapshot["tx"])
        # Not shell text: filenames remain separate arguments, no command executes.
        expected = plan["expected_tx"]
        result["proposed_arm_argv"] = ["./bin/arm-tx-source", "--run", wave["raw_file"],
             str(wave["sample_count"]), str(expected["sample_rate_hz"]), str(expected["tx_lo_hz"]),
             str(expected["tx_rf_bandwidth_hz"]), str(expected["tx_hardwaregain_db"]),
             str(plan["duration_seconds"]), expected["guard_identity"], expected["tx_rf_port"],
             wave["raw_sha256"], "RF_LINK_REVIEWED"]
        result["snapshot_note"] = "Saved readback may become stale; native program rechecks RF settings. Serial and wiring must be rechecked at connection."
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    out = args.output or ROOT / "results" / ("p12-readonly-" + stamp)
    out.mkdir(parents=True, exist_ok=False)
    report = dict(started_utc=datetime.now(timezone.utc).isoformat(), uri=args.uri,
                  status="inspection_failed", read_only=True, rf_transmitted=False)
    try:
        with use_libiio(args.libiio_dir):
            import iio
            ctx = iio.Context(args.uri)
            try:
                ctx.set_timeout(3000)
                report.update(inspect_context(ctx))
                (out / "context.xml").write_text(ctx.xml, encoding="utf-8")
            finally:
                ctx = None
        report["status"] = "readonly_inspection_passed"
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
    report["finished_utc"] = datetime.now(timezone.utc).isoformat()
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(dict(output=str(out), **report), ensure_ascii=False, indent=2))
    if report["status"] != "readonly_inspection_passed":
        sys.exit(1)


if __name__ == "__main__":
    main()
