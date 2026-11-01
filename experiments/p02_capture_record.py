"""Capture one AD9361 RX I/Q frame with settings; never transmit or retune."""

import argparse
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

import numpy as np

from rfsig.iio_runtime import use_libiio
from rfsig.iq_recording import load_iq_record, save_iq_record


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLES = 1024


def _settings(sdr) -> dict[str, object]:
    return {
        "sample_rate_hz": int(sdr.sample_rate),
        "rx_lo_hz": int(sdr.rx_lo),
        "rx_rf_bandwidth_hz": int(sdr.rx_rf_bandwidth),
        "gain_control_mode": sdr.gain_control_mode_chan0,
        # Under AGC this is an instantaneous readback, not a fixed gain setting.
        "gain_readback_db": float(sdr.rx_hardwaregain_chan0),
    }


def _scan_format(context, name: str) -> dict[str, object]:
    device = context.find_device("cf-ad9361-lpc")
    channel = next(
        (ch for ch in device.channels if ch.id == name and not ch.output), None
    )
    if channel is None or not channel.scan_element:
        raise RuntimeError(f"RX scan channel {name} is unavailable")
    fmt = channel.data_format
    return {
        "valid_bits": fmt.bits,
        "storage_bits": fmt.length,
        "shift": fmt.shift,
        "signed": fmt.is_signed,
        "endian": "big" if fmt.is_be else "little",
        "repeat": fmt.repeat,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--libiio-dir", required=True, type=Path)
    parser.add_argument("--uri", default="ip:192.168.2.1")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    capture_id = datetime.now(timezone.utc).strftime("p02-%Y%m%dT%H%M%S%fZ")
    output = args.output or (PROJECT_ROOT / "results" / capture_id)

    with use_libiio(args.libiio_dir):
        import adi
        import iio

        sdr = adi.ad9361(uri=args.uri)
        try:
            context = sdr.ctx
            model = context.attrs.get("hw_model")
            if model != "PUZHI PZSDR P201":
                raise RuntimeError(f"Expected P201 IIO context, got {model!r}")
            if context.find_device("ad9361-phy") is None:
                raise RuntimeError("AD9361 RF control device is missing")
            if context.find_device("cf-ad9361-lpc") is None:
                raise RuntimeError("AD9361 RX sample device is missing")

            scan_format = {
                name: _scan_format(context, name)
                for name in ("voltage0", "voltage1")
            }
            sdr.rx_enabled_channels = [0]
            sdr.rx_buffer_size = SAMPLES
            before = _settings(sdr)

            start_utc = datetime.now(timezone.utc).isoformat(timespec="microseconds")
            start_wall = perf_counter()
            try:
                iq = np.asarray(sdr.rx()).copy()
            except Exception as error:
                raise RuntimeError(
                    "RX capture failed. If IIO Oscilloscope is capturing, "
                    "stop Capture in its window before retrying."
                ) from error
            elapsed = perf_counter() - start_wall
            end_utc = datetime.now(timezone.utc).isoformat(timespec="microseconds")
            after = _settings(sdr)

            if iq.shape != (SAMPLES,) or not np.iscomplexobj(iq):
                raise RuntimeError(f"Unexpected RX shape or type: {iq.shape}, {iq.dtype}")
            for key in ("sample_rate_hz", "rx_lo_hz", "rx_rf_bandwidth_hz", "gain_control_mode"):
                if before[key] != after[key]:
                    raise RuntimeError(f"RX setting changed during capture: {key}")

            metadata = {
                "capture_start_utc": start_utc,
                "capture_end_utc": end_utc,
                "capture_id": capture_id,
                "capture_call_wall_seconds": elapsed,
                "sample_window_seconds": iq.size / before["sample_rate_hz"],
                "iio_uri": args.uri,
                "board_model": model,
                "board_firmware_version": context.attrs.get("fw_version"),
                "board_kernel": context.attrs.get("local,kernel"),
                "iio_server_version": list(context.version),
                "iio_client_version": list(iio.version),
                "control_device": "ad9361-phy",
                "sample_device": "cf-ad9361-lpc",
                "rx_channel_index": 0,
                "component_channels": ["voltage0", "voltage1"],
                "component_mapping": "real=voltage0; imag=voltage1 (pyadi-iio mapping)",
                "scan_format": scan_format,
                "buffer_samples": SAMPLES,
                "rx_output_type": sdr.rx_output_type,
                "sample_units": "unscaled raw receive counts; not volts or dBm",
                "settings_before": before,
                "settings_after": after,
                "gain_note": "With AGC, gain readbacks are snapshots, not fixed settings.",
                "input_note": "No known RF stimulus or modulation label was supplied.",
            }
        finally:
            sdr.rx_destroy_buffer()
            sdr.close()

    saved = save_iq_record(output, iq, metadata)
    replay, replay_metadata = load_iq_record(output)
    np.testing.assert_array_equal(replay, iq)
    if replay.dtype != iq.dtype or replay_metadata != saved:
        raise RuntimeError("Saved I/Q or metadata does not match the in-memory capture")

    print("记录目录：", output.resolve())
    print("板卡：", saved["board_model"])
    print("样本：", saved["sample_count"], saved["sample_dtype"])
    print("I/Q 格式：", saved["scan_format"])
    print("采样前配置：", saved["settings_before"])
    print("采样后配置：", saved["settings_after"])
    print("前 5 个样本：", iq[:5])
    print("样本有变化：", bool(np.any(iq != iq[0])))
    print("保存与立即回读：逐点相同，SHA256 校验通过")


if __name__ == "__main__":
    main()
