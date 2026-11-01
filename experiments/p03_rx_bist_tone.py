"""Temporarily inject an AD9361 RX digital test tone and verify RX I/Q.

This does not transmit samples or validate the external RF signal path.
"""

import argparse
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from rfsig.iio_runtime import use_libiio
from rfsig.iq_recording import load_iq_record, save_iq_record


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLES = 1024


def _mode_is_off(value: str) -> bool:
    return value.strip().split()[:1] == ["0"]


def _peak(iq: np.ndarray, sample_rate_hz: int) -> dict[str, float]:
    spectrum = np.fft.fftshift(np.fft.fft(iq)) / iq.size
    frequencies = np.fft.fftshift(np.fft.fftfreq(iq.size, 1 / sample_rate_hz))
    magnitudes = np.abs(spectrum)
    peak_index = int(np.argmax(magnitudes))
    return {
        "frequency_hz": float(frequencies[peak_index]),
        "magnitude_raw_counts": float(magnitudes[peak_index]),
        "median_bin_magnitude_raw_counts": float(np.median(magnitudes)),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--libiio-dir", required=True, type=Path)
    parser.add_argument("--uri", default="ip:192.168.2.1")
    parser.add_argument("--frequency-code", type=int, choices=(0, 1, 2, 3), default=0)
    parser.add_argument("--level-dbfs", type=int, choices=(0, 6, 12, 18), default=6)
    args = parser.parse_args()

    with use_libiio(args.libiio_dir):
        import adi

        sdr = adi.ad9361(uri=args.uri)
        tone = None
        captured: list[np.ndarray] = []
        original = None
        restored = None
        may_have_enabled = False
        try:
            context = sdr.ctx
            context.set_timeout(3000)
            if context.attrs.get("hw_model") != "PUZHI PZSDR P201":
                raise RuntimeError("Refusing RX BIST: IIO context is not the checked P201")
            phy = context.find_device("ad9361-phy")
            rx = context.find_device("cf-ad9361-lpc")
            dds = context.find_device("cf-ad9361-dds-core-lpc")
            if phy is None or rx is None or dds is None:
                raise RuntimeError("Required AD9361 control/RX/DDS device is missing")
            required = ("bist_tone", "bist_prbs", "loopback")
            if any(name not in phy.debug_attrs for name in required):
                raise RuntimeError("Required AD9361 debug attribute is missing")
            tone = phy.debug_attrs["bist_tone"]
            original = tone.value.strip()
            if not all(
                _mode_is_off(phy.debug_attrs[name].value)
                for name in required
            ):
                raise RuntimeError("Existing BIST or loopback mode is active; no setting changed")
            dds_scales = {
                ch.id: float(ch.attrs["scale"].value)
                for ch in dds.channels
                if ch.output and ch.id.startswith("altvoltage") and "scale" in ch.attrs
            }
            if not dds_scales or any(scale != 0.0 for scale in dds_scales.values()):
                raise RuntimeError("TX DDS tone is active or unreadable; no setting changed")

            sample_rate_hz = int(sdr.sample_rate)
            if sample_rate_hz <= 0:
                raise RuntimeError("Invalid sample rate")
            sdr.rx_enabled_channels = [0]
            sdr.rx_buffer_size = SAMPLES
            frequency_fractions = (1 / 32, 1 / 16, 3 / 32, 1 / 8)
            expected_hz = sample_rate_hz * frequency_fractions[args.frequency_code]
            tone_command = f"2 {args.frequency_code} {args.level_dbfs} 0"
            print(f"RX BIST: Fs={sample_rate_hz} Hz, expected |tone|={expected_hz:g} Hz")
            print("RX BIST: enabling receive-side digital injection only")
            may_have_enabled = True
            tone.value = tone_command
            for _ in range(2):
                frame = np.asarray(sdr.rx()).copy()
                if frame.shape != (SAMPLES,) or not np.iscomplexobj(frame):
                    raise RuntimeError(f"Unexpected RX frame: {frame.shape}, {frame.dtype}")
                captured.append(frame)
        finally:
            # The RX test source is temporary even when capture or validation fails.
            try:
                if may_have_enabled and tone is not None:
                    tone.value = "0 0 0 0"
                    restored = tone.value.strip()
            finally:
                try:
                    sdr.rx_destroy_buffer()
                finally:
                    sdr.close()

    if restored is None or not _mode_is_off(restored):
        raise RuntimeError(f"RX BIST did not confirm disabled: {restored!r}")
    if len(captured) != 2:
        raise RuntimeError(f"Expected two RX frames, captured {len(captured)}")

    peaks = [_peak(frame, sample_rate_hz) for frame in captured]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    frequency_bin_hz = sample_rate_hz / SAMPLES
    peak_matches = all(
        abs(abs(peak["frequency_hz"]) - expected_hz) <= frequency_bin_hz / 2
        for peak in peaks
    )
    for index, frame in enumerate(captured, start=1):
        target = (
            PROJECT_ROOT
            / "results"
            / f"p03-rx-bist-f{args.frequency_code}-l{args.level_dbfs}-{stamp}-frame{index}"
        )
        metadata = {
            "capture_kind": "AD9361 RX-side digital BIST tone; not an external RF signal",
            "board_model": "PUZHI PZSDR P201",
            "iio_uri": args.uri,
            "sample_rate_hz": sample_rate_hz,
            "sample_count_requested": SAMPLES,
            "rx_channel_index": 0,
            "bist_tone_command": tone_command,
            "bist_tone_before": original,
            "bist_tone_after": restored,
            "tx_dds_scales_before": dds_scales,
            "expected_absolute_frequency_hz": expected_hz,
            "fft_bin_spacing_hz": frequency_bin_hz,
            "fft_peak": peaks[index - 1],
            "external_rf_path_tested": False,
        }
        save_iq_record(target, frame, metadata)
        replay, _ = load_iq_record(target)
        np.testing.assert_array_equal(replay, frame)
        print(f"Frame {index}: peak={peaks[index - 1]['frequency_hz']:g} Hz; saved={target}")
    print(
        f"BIST disabled, readback={restored!r}; "
        f"peak matches expected |{expected_hz:g} Hz|={peak_matches}"
    )
    if not peak_matches:
        raise RuntimeError("RX BIST peak differs from the selected expected frequency")


if __name__ == "__main__":
    main()
