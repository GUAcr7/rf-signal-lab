"""Finite RX check: 32 blocks, stop after 8, reopen for 32; no GUI or RF writes."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from threading import Event

import numpy as np

from rfsig.bandwidth import occupied_bandwidth
from rfsig.rx_monitor import P201Receiver, run_monitor_session, save_monitor_snapshot


ROOT = Path(__file__).resolve().parents[1]


def verify_record(directory):
    report = json.loads((directory/"report.json").read_text(encoding="utf-8"))
    with (directory/"monitor.npz").open("rb") as stream:
        assert hashlib.file_digest(stream, "sha256").hexdigest() == report["arrays_sha256"]
    with np.load(directory/"monitor.npz", allow_pickle=False) as saved:
        iq, psd, freq = saved["iq_frames"], saved["psd_frames"], saved["frequency_hz"]
        fs, n = report["settings"]["sample_rate_hz"], report["fft_size"]
        assert iq.shape == (report["frame_count"], n) and np.isfinite(iq).all()
        weights = 0.5-0.5*np.cos(2*np.pi*np.arange(n)/n)
        independent = np.abs(np.fft.fftshift(np.fft.fft(iq*weights, axis=1), axes=1))**2/(fs*np.sum(weights**2))
        np.testing.assert_allclose(psd, independent, rtol=3e-15, atol=0)
        powers = np.mean(iq.real**2+iq.imag**2, axis=1)
        np.testing.assert_array_equal(powers, saved["mean_power"])
        for i, row in enumerate(psd):
            band = occupied_bandwidth(freq, row, tuple(report["analysis_band_hz"]),
                                      rf_lo_hz=report["settings"]["rx_lo_hz"])
            for key in ("bandwidth_hz", "center_baseband_hz", "lower_hz", "upper_hz"):
                np.testing.assert_allclose(getattr(band, key), report["bandwidths"][i][key], rtol=1e-12, atol=1e-6)
            ref = report["power_reference"]
            if powers[i] > 0 and ref is not None:
                np.testing.assert_allclose(10*np.log10(powers[i]/ref), report["relative_db"][i], atol=1e-12)
        assert np.all(saved["host_rx_end_seconds"] >= saved["host_rx_start_seconds"])
        assert np.all(np.diff(saved["host_rx_end_seconds"]) > 0)
        unique = len({row.tobytes() for row in iq})
    return {"frame_count": report["frame_count"], "state": report["state"],
            "context_released": report["receive_context_released"],
            "unique_blocks": unique, "all_saved_blocks_recomputed": True,
            "observed_blocks_per_host_second": report["observed_blocks_per_host_second"],
            "host_elapsed_to_last_rx_seconds": report["host_elapsed_to_last_rx_seconds"],
            "sample_time_sum_seconds": report["sum_of_block_sample_durations_seconds"],
            "error": report["error"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--libiio-dir", required=True, type=Path)
    parser.add_argument("--uri", default="ip:192.168.2.1")
    args = parser.parse_args()
    out = ROOT/"results"/datetime.now(timezone.utc).strftime("p05-rx-monitor-check-%Y%m%dT%H%M%S%fZ")
    out.mkdir()
    checks = []
    for number, stop_after in enumerate((None, 8, None), 1):
        stop = Event()
        def observe(snapshot):
            if stop_after is not None and snapshot[0]["frame_count"] >= stop_after:
                stop.set()
        session = run_monitor_session(lambda: P201Receiver(args.libiio_dir, args.uri),
                                      frame_limit=32, interval_seconds=0, stop_event=stop, on_snapshot=observe)
        target = save_monitor_snapshot(session.snapshot(), out/f"session-{number}")
        item = verify_record(target)
        expected_count = 8 if stop_after else 32
        expected_state = "stopped" if stop_after else "limit_reached"
        item["passed"] = (item["frame_count"] == expected_count and item["state"] == expected_state
                          and item["context_released"] and item["unique_blocks"] > 1 and not item["error"])
        checks.append(item)
        print(f"Session {number}: {json.dumps(item)}", flush=True)
        if not item["passed"]:
            break
    summary = {"scope": "finite repeated RX blocks; not full-rate uninterrupted ADC recording or actual GUI testing",
               "sessions": checks, "passed": len(checks) == 3 and all(x["passed"] for x in checks),
               "hardware_continuity_verified": False, "ai_connected": False, "tx_started": False,
               "gui_verified": False,
               "source_code_sha256": {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
                                      for name in ("src/rfsig/rx_monitor.py", "experiments/p05_rx_monitor_check.py")}}
    (out/"verification.json").write_text(json.dumps(summary, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print("Evidence:", out, flush=True)
    if not summary["passed"]:
        raise RuntimeError("Finite RX check did not pass; inspect saved evidence")


if __name__ == "__main__":
    main()
