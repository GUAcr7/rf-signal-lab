"""Read P201 RF settings and scan formats without configuring or transmitting."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from rfsig.iio_runtime import use_libiio


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _channel(device, name: str, output: bool):
    channel = next(
        (ch for ch in device.channels if ch.id == name and ch.output == output), None
    )
    if channel is None:
        raise RuntimeError(f"Missing {'TX' if output else 'RX'} channel {name}")
    return channel


def _scan_format(channel) -> dict[str, object]:
    fmt = channel.data_format
    return {
        "valid_bits": fmt.bits,
        "storage_bits": fmt.length,
        "signed": fmt.is_signed,
        "shift": fmt.shift,
        "endian": "big" if fmt.is_be else "little",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--libiio-dir", required=True, type=Path)
    parser.add_argument("--uri", default="ip:192.168.2.1")
    args = parser.parse_args()

    with use_libiio(args.libiio_dir):
        import adi
        import iio

        sdr = adi.ad9361(uri=args.uri)
        try:
            context = sdr.ctx
            phy = context.find_device("ad9361-phy")
            rx_device = context.find_device("cf-ad9361-lpc")
            tx_device = context.find_device("cf-ad9361-dds-core-lpc")
            if phy is None or rx_device is None or tx_device is None:
                raise RuntimeError("P201 AD9361 control/RX/TX IIO device is missing")

            rx_phy = _channel(phy, "voltage0", False)
            tx_phy = _channel(phy, "voltage0", True)
            report = {
                "read_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "read_only": True,
                "board_model": context.attrs.get("hw_model"),
                "board_firmware_version": context.attrs.get("fw_version"),
                "board_kernel": context.attrs.get("local,kernel"),
                "iio_uri": args.uri,
                "iio_server_version": list(context.version),
                "iio_client_version": list(iio.version),
                "sample_rate_hz": int(sdr.sample_rate),
                "tx_lo_hz": int(sdr.tx_lo),
                "rx_lo_hz": int(sdr.rx_lo),
                "tx_rf_bandwidth_hz": int(sdr.tx_rf_bandwidth),
                "rx_rf_bandwidth_hz": int(sdr.rx_rf_bandwidth),
                "tx_hardwaregain_db": float(sdr.tx_hardwaregain_chan0),
                "rx_gain_mode": sdr.gain_control_mode_chan0,
                "rx_gain_readback_db": float(sdr.rx_hardwaregain_chan0),
                "gain_note": "RX AGC gain is an instantaneous readback; TX hardwaregain is attenuation.",
                "tx_rf_port_select": tx_phy.attrs["rf_port_select"].value,
                "rx_rf_port_select": rx_phy.attrs["rf_port_select"].value,
                "rx_scan_format": {
                    name: _scan_format(_channel(rx_device, name, False))
                    for name in ("voltage0", "voltage1")
                },
                "tx_scan_format": {
                    name: _scan_format(_channel(tx_device, name, True))
                    for name in ("voltage0", "voltage1")
                },
            }
        finally:
            sdr.close()

    if report["board_model"] != "PUZHI PZSDR P201":
        raise RuntimeError(f"Unexpected IIO board: {report['board_model']!r}")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = PROJECT_ROOT / "results" / f"p03-rf-preflight-{stamp}.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("只读记录：", output)


if __name__ == "__main__":
    main()
