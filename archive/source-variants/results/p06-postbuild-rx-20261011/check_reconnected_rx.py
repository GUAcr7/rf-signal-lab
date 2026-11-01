"""Fresh P201 discovery and one bounded RX block; never writes RF/TX attributes."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import subprocess
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))
from rfsig.iio_runtime import use_libiio
from rfsig.rx_monitor import P201Receiver, run_monitor_session, save_monitor_snapshot

DLL_DIR = Path(r"D:\FPGA natch\IIO-Oscilloscope-v0.18-portable\app\bin")
URI = "ip:192.168.2.1"


def digest(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def context_readback():
    with use_libiio(DLL_DIR):
        import iio
        context = iio.Context(URI)
        context.set_timeout(3000)
        phy = context.find_device("ad9361-phy")
        rx = context.find_device("cf-ad9361-lpc")
        tx = context.find_device("cf-ad9361-dds-core-lpc")
        result = {
            "checked_at_utc": datetime.now(timezone.utc).isoformat(),
            "uri": URI,
            "context_attributes": {k: context.attrs.get(k) for k in
                ("hw_model", "fw_version", "local,kernel", "hw_serial", "hw_model_variant")},
            "iio_client_version": list(iio.version),
            "iio_server_version": list(context.version),
            "devices": [{"id": d.id, "name": d.name} for d in context.devices],
        }
        if result["context_attributes"]["hw_model"] != "PUZHI PZSDR P201" or any(d is None for d in (phy, rx, tx)):
            raise RuntimeError("Context does not match the previously verified P201 devices")
        rx0 = phy.find_channel("voltage0", False)
        lo = phy.find_channel("altvoltage0", True)
        result["rx_configuration"] = {
            "sample_rate_hz": int(rx0.attrs["sampling_frequency"].value),
            "rx_lo_hz": int(lo.attrs["frequency"].value),
            "rx_rf_bandwidth_hz": int(rx0.attrs["rf_bandwidth"].value),
            "gain_control_mode": rx0.attrs["gain_control_mode"].value,
            "hardware_gain_db": float(rx0.attrs["hardwaregain"].value.split()[0]),
            "rf_port_select": rx0.attrs["rf_port_select"].value,
        }
        result["rx_scan_channels"] = []
        for channel in rx.channels:
            if not channel.output and channel.scan_element:
                fmt = channel.data_format
                result["rx_scan_channels"].append({"id": channel.id, "name": channel.name,
                    "bits": fmt.bits, "storage_bits": fmt.length, "shift": fmt.shift,
                    "signed": fmt.is_signed, "big_endian": fmt.is_be, "repeat": fmt.repeat})
        result["debug_modes"] = {k: phy.debug_attrs[k].value for k in ("bist_tone", "bist_prbs", "loopback")}
        result["dds_scales"] = {c.id: c.attrs["scale"].value for c in tx.channels
                                if c.output and c.id.startswith("altvoltage") and "scale" in c.attrs}
        return result


def main():
    report = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Fresh device/configuration readbacks and one RX-only 1024-sample block",
        "rf_attributes_written": False, "tx_started": False,
        "bist_invoked": False, "gui_operated": False,
        "source_sha256": {str(p.relative_to(ROOT)): digest(p) for p in
            (ROOT/"src/rfsig/iio_runtime.py", ROOT/"src/rfsig/rx_monitor.py", Path(__file__))},
        "selected_dll_path": str(DLL_DIR/"libiio.dll"),
        "selected_dll_sha256": digest(DLL_DIR/"libiio.dll"),
        "implementation_review": "Reviewed P201Receiver, context_manager, ad936x, RX buffer initialization and DDS helpers. Constructor performs context/device selection and client buffer setup; RX call enables RX scan elements and fills a receive buffer. No RF property setters, TX buffer, DDS setters or BIST writes are invoked.",
    }
    try:
        report["before"] = context_readback()
        print("DISCOVERY", json.dumps(report["before"], ensure_ascii=False), flush=True)
        session = run_monitor_session(lambda: P201Receiver(DLL_DIR, URI), frame_limit=1, interval_seconds=0)
        snapshot = session.snapshot()
        if snapshot[0]["frame_count"]:
            out = save_monitor_snapshot(snapshot, HERE/"short-rx")
            with np.load(out/"monitor.npz", allow_pickle=False) as saved:
                iq = saved["iq_frames"]
                sample = {
                    "shape": list(iq.shape), "dtype": str(iq.dtype),
                    "finite": bool(np.isfinite(iq).all()), "complex": bool(np.iscomplexobj(iq)),
                    "varies_within_block": bool(np.any(iq[0] != iq[0, 0])),
                    "distinct_complex_samples": len(np.unique(iq[0])),
                    "integer_raw_counts": bool(np.all(iq.real == np.round(iq.real)) and np.all(iq.imag == np.round(iq.imag))),
                    "i_min_max": [float(iq.real.min()), float(iq.real.max())],
                    "q_min_max": [float(iq.imag.min()), float(iq.imag.max())],
                    "first_five_iq": [[float(v.real), float(v.imag)] for v in iq[0, :5]],
                    "npz_sha256": digest(out/"monitor.npz"),
                    "stored_hash_matches": digest(out/"monitor.npz") == snapshot[0].get("arrays_sha256", digest(out/"monitor.npz")),
                }
            stored = json.loads((out/"report.json").read_text(encoding="utf-8"))
            sample["stored_hash_matches"] = sample["npz_sha256"] == stored["arrays_sha256"]
            report["sample"] = sample
            report["capture_report"] = stored
        else:
            report["capture_report"] = snapshot[0]
        report["after"] = context_readback()
        before = dict(report["before"]["rx_configuration"])
        after = dict(report["after"]["rx_configuration"])
        before.pop("hardware_gain_db", None)
        after.pop("hardware_gain_db", None)
        report["rx_configuration_readbacks_unchanged_except_agc_gain"] = before == after
        report["debug_modes_readbacks_unchanged"] = report["before"]["debug_modes"] == report["after"]["debug_modes"]
        report["dds_scale_readbacks_unchanged"] = report["before"]["dds_scales"] == report["after"]["dds_scales"]
        report["passed"] = bool(report.get("sample", {}).get("finite") and report["sample"]["complex"]
            and report["sample"]["shape"] == [1, 1024] and report["sample"]["varies_within_block"]
            and report["sample"]["integer_raw_counts"] and report["sample"]["stored_hash_matches"]
            and stored["receive_context_released"] and stored["error"] is None
            and report["rx_configuration_readbacks_unchanged_except_agc_gain"]
            and report["debug_modes_readbacks_unchanged"] and report["dds_scale_readbacks_unchanged"])
        report["limitations"] = ["One block proves short RX availability, not continuous gap-free ADC capture.",
            "RF input/target and power calibration are unknown; no known-signal or AI acceptance.",
            "No board shell, runtime libc, persistent mount or ARM application was verified by IIO discovery."]
    except Exception as error:
        report["passed"] = False
        report["error"] = f"{type(error).__name__}: {error}"
    (HERE/"recovery-verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "error": report.get("error"), "sample": report.get("sample"),
        "evidence": str(HERE)}, ensure_ascii=False), flush=True)
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
