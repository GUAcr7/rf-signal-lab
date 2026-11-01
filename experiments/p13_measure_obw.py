"""Measure 99% occupied bandwidth of the shipped TX waveforms, host-side.

Why host-side first: the analyser's OBW function reads the RF spectrum after the
DAC, PA and cable, so it shows what actually left the connector. This script
reads the exact bytes that were transmitted, so it establishes the digital
reference those RF readings must be compared against. If the two disagree by more
than the instrument's resolution, that itself is a finding.

What it computes per waveform:
  * Welch PSD (Hann, 50% overlap) on the full 131072-sample buffer
  * 99% occupied bandwidth via rfsig.bandwidth.occupied_bandwidth
  * three candidate centre-frequency estimators, to show they are NOT equivalent:
      - peak bin            (what a spectrum analyser's Peak Search reports)
      - spectral centroid   (power-weighted mean)
      - OBW midpoint        (equal-tail 0.5%/99.5% midpoint) <- the method p05b uses
  * a comparison against the theoretical Rs*(1+beta) for the shaped waveforms

Offline only. Reads files, writes a report, never touches a device.
"""

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from rfsig.bandwidth import occupied_bandwidth, rrc_occupied_bandwidth_hz
from rfsig.spectrum import welch_power_spectrum

ROOT = Path(__file__).resolve().parents[1]

SAMPLE_RATE_HZ = 30_720_000
SAMPLE_COUNT = 131_072
SAMPLES_PER_SYMBOL = 128
SYMBOL_RATE_HZ = SAMPLE_RATE_HZ / SAMPLES_PER_SYMBOL   # 240 000
ROLLOFF = 0.35
TX_LO_HZ = 2_450_000_000

WAVEFORMS = {
    "tone-positive.iq16le": dict(kind="tone", offset_hz=960_000),
    "tone-negative.iq16le": dict(kind="tone", offset_hz=-960_000),
    "tone-double-offset.iq16le": dict(kind="tone", offset_hz=1_920_000),
    "bpsk.iq16le": dict(kind="shaped", offset_hz=960_000, bits=1),
    "qpsk.iq16le": dict(kind="shaped", offset_hz=960_000, bits=2),
    "qam16.iq16le": dict(kind="shaped", offset_hz=960_000, bits=4),
}

SOURCES = {
    "tone-positive.iq16le": "results/p13-waveform-bundle-20261016/waveforms-existing30m72.tar",
    "tone-negative.iq16le": "results/p13-followup-waveforms-20261016T094225Z/followup-waveforms.tar",
    "tone-double-offset.iq16le": "results/p13-agility-bundle-20261016/agility.tar",
    "bpsk.iq16le": "results/p13-followup-waveforms-20261016T094225Z/followup-waveforms.tar",
    "qpsk.iq16le": "results/p13-followup-waveforms-20261016T094225Z/followup-waveforms.tar",
    "qam16.iq16le": "results/p13-followup-waveforms-20261016T094225Z/followup-waveforms.tar",
}
MEMBERS = {
    "tone-positive.iq16le": "existing30m72/tone-positive.iq16le",
    "tone-negative.iq16le": "bundle/tone-negative.iq16le",
    "tone-double-offset.iq16le": "agility/tone-double-offset.iq16le",
    "bpsk.iq16le": "bundle/bpsk.iq16le",
    "qpsk.iq16le": "bundle/qpsk.iq16le",
    "qam16.iq16le": "bundle/qam16.iq16le",
}
EXPECTED_SHA256 = {
    "tone-positive.iq16le": "36cd4ed7007721dd023b7b2c8b581a5ddb6f0365d9c0c0a40fef7c87522a0727",
    "tone-negative.iq16le": "9bf8bb37bb59d05955cef616a19e9d5595e29e1b9b39cb9a47ee3d256a92e57d",
    "tone-double-offset.iq16le": "4aa0564fc0061ca2410795222637f812e8d246fc42ae7c6a088f18b9e6ec6362",
    "bpsk.iq16le": "ceebe58f146a1cde27bc91b429e3ca26c6ecec5b1917d528d01ce75a2d652789",
    "qpsk.iq16le": "fd56491f068881c5c315fc4fba41bfd165b0e3e25419d66755e66c372081cee9",
    "qam16.iq16le": "85f8df7f3f5e986678df225da3f3421ecc453891284b12ca9ad67895be26efc2",
}


def load_waveform(name: str) -> np.ndarray:
    import tarfile
    with tarfile.open(ROOT / SOURCES[name]) as tar:
        raw = tar.extractfile(MEMBERS[name]).read()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != EXPECTED_SHA256[name]:
        raise RuntimeError(f"{name}: sha256 {digest} != expected {EXPECTED_SHA256[name]}")
    words = np.frombuffer(raw, dtype="<i2")
    if words.size != SAMPLE_COUNT * 2:
        raise RuntimeError(f"{name}: unexpected word count {words.size}")
    i = words[0::2].astype(np.float64)
    q = words[1::2].astype(np.float64)
    return i + 1j * q


def welch_psd(x: np.ndarray, nperseg: int = 4096):
    """Two-sided complex Welch PSD via the shared implementation.

    This used to be a local copy that multiplied every bin except DC and the
    last by 2.0. That is the real-signal one-sided convention; the input here is
    complex I/Q whose spectrum is not conjugate-symmetric, so the doubling
    inflated almost all bins and left the two undoubled bins (0 Hz and -7.5 kHz,
    both inside our analysis band) sitting at half weight.

    ``rfsig.spectrum.welch_power_spectrum`` is power-normalised, complex-aware
    and covered by conservation tests in ``tests/test_spectrum.py``.
    """
    spectrum = welch_power_spectrum(x, SAMPLE_RATE_HZ, nperseg, overlap=0.5)
    return spectrum


def measure(name: str) -> dict:
    spec = WAVEFORMS[name]
    x = load_waveform(name)
    spectrum = welch_psd(x)
    freqs, psd = spectrum.frequency_hz, spectrum.psd
    segments = 1 + (len(x) - spectrum.sample_count) // (spectrum.sample_count // 2)

    # Power conservation: the integral of the two-sided PSD must reproduce the
    # window-weighted mean power of the analysed samples. A one-sided doubling
    # would put this ratio near 2.
    conservation = float(spectrum.bin_power.sum()) / spectrum.window_weighted_mean_power
    if not 0.99 <= conservation <= 1.01:
        raise RuntimeError(f"{name}: PSD power conservation off by {conservation:.4f}x")

    offset = float(spec["offset_hz"])
    # Analysis band around the carrier, wide enough for the RRC support plus
    # sidelobes but far from the Nyquist edges.
    half_band = 1_000_000.0
    low, high = offset - half_band, offset + half_band
    if low <= freqs[0] or high >= freqs[-1]:
        raise RuntimeError(f"{name}: analysis band falls outside the observed span")

    obw = occupied_bandwidth(freqs, psd, (low, high), occupied_fraction=0.99,
                             noise_floor_psd=0.0, min_effective_power=0.0,
                             rf_lo_hz=TX_LO_HZ)
    if obw.status != "ok":
        raise RuntimeError(f"{name}: occupied bandwidth status {obw.status}")

    # Three centre estimators, deliberately computed on the same PSD.
    in_band = (freqs >= low) & (freqs <= high)
    f_band, p_band = freqs[in_band], psd[in_band]
    peak_centre = float(f_band[int(np.argmax(p_band))])
    centroid = float(np.sum(f_band * p_band) / np.sum(p_band))

    shaped = spec["kind"] == "shaped"
    theory_support = (SYMBOL_RATE_HZ * (1 + ROLLOFF)) if shaped else None
    theory_99 = rrc_occupied_bandwidth_hz(0.99, SYMBOL_RATE_HZ, ROLLOFF) if shaped else None
    result = {
        "waveform": name,
        "kind": spec["kind"],
        "target_offset_hz": offset,
        "welch_segments": segments,
        "welch_nperseg": len(freqs),
        "welch_bin_hz": SAMPLE_RATE_HZ / len(freqs),
        "psd_power_conservation_ratio": conservation,
        "psd_total_power": float(spectrum.bin_power.sum()),
        "psd_window_weighted_power": spectrum.window_weighted_mean_power,
        "psd_convention": "two_sided_complex_no_doubling",
        "analysis_band_hz": [low, high],
        "obw_99_bandwidth_hz": obw.bandwidth_hz,
        "obw_99_lower_hz": obw.lower_hz,
        "obw_99_upper_hz": obw.upper_hz,
        "centre_peak_hz": peak_centre,
        "centre_centroid_hz": centroid,
        "centre_obw_midpoint_hz": obw.center_baseband_hz,
        "centre_rf_if_lo_2450GHz": obw.center_rf_hz,
        "theory_support_hz": theory_support,
        "theory_99_obw_hz": theory_99,
        "source_tar": SOURCES[name],
        "source_member": MEMBERS[name],
        "sha256": EXPECTED_SHA256[name],
    }
    if shaped:
        result["obw_99_vs_theory99_hz"] = obw.bandwidth_hz - theory_99
        result["obw_99_vs_theory99_pct"] = 100.0 * (obw.bandwidth_hz - theory_99) / theory_99
        result["support_minus_theory99_hz"] = theory_support - theory_99
    # How far each estimator sits from the commanded offset.
    result["centre_error_peak_hz"] = peak_centre - offset
    result["centre_error_centroid_hz"] = centroid - offset
    result["centre_error_obw_midpoint_hz"] = obw.center_baseband_hz - offset
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    out = args.output or ROOT / "results" / datetime.now(timezone.utc).strftime("p13-obw-%Y%m%dT%H%M%SZ")
    out.mkdir(parents=True, exist_ok=False)

    results = [measure(name) for name in WAVEFORMS]
    report = {
        "schema": "rfsig.obw_measurement.v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "99% occupied bandwidth of the exact transmitted bytes, computed host-side",
        "not_a_substitute_for": "the RF measurement at the connector; PA and cable are not included",
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "symbol_rate_hz": SYMBOL_RATE_HZ,
        "rolloff": ROLLOFF,
        "theory_support_hz": SYMBOL_RATE_HZ * (1 + ROLLOFF),
        "theory_99_obw_hz": rrc_occupied_bandwidth_hz(0.99, SYMBOL_RATE_HZ, ROLLOFF),
        "theory_note": "Rs*(1+beta) is the theoretical RRC *support* where the spectrum reaches zero. "
                       "It is NOT the 99% containment bandwidth: for the ideal raised-cosine spectrum the "
                       "99% width is smaller (about 280 kHz vs 324 kHz at beta=0.35). The 99% figure is "
                       "solved analytically in rrc_obw_fraction_hz and is the number to compare against.",
        "device_accessed": False,
        "results": results,
    }
    (out / "obw.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"{'waveform':26s} {'99% OBW':>10s} {'theory99':>10s} {'diff':>8s} {'vs%':>7s} "
          f"{'peakerr':>9s} {'centerr':>9s} {'midErr':>8s}")
    for r in results:
        if r["kind"] == "shaped":
            print(f"{r['waveform']:26s} {r['obw_99_bandwidth_hz']:10.0f} {r['theory_99_obw_hz']:10.0f} "
                  f"{r['obw_99_vs_theory99_hz']:+8.0f} {r['obw_99_vs_theory99_pct']:+7.2f} "
                  f"{r['centre_error_peak_hz']:+9.0f} {r['centre_error_centroid_hz']:+9.0f} "
                  f"{r['centre_error_obw_midpoint_hz']:+8.0f}")
        else:
            print(f"{r['waveform']:26s} {r['obw_99_bandwidth_hz']:10.0f} {'(tone)':>10s} "
                  f"{'-':>8s} {'-':>7s} {r['centre_error_peak_hz']:+9.0f} "
                  f"{r['centre_error_centroid_hz']:+9.0f} {r['centre_error_obw_midpoint_hz']:+8.0f}")
    print(f"\ntheory: support Rs*(1+beta)={SYMBOL_RATE_HZ*(1+ROLLOFF):.0f} Hz, "
          f"99% containment={rrc_occupied_bandwidth_hz(0.99, SYMBOL_RATE_HZ, ROLLOFF):.0f} Hz")
    print(f"evidence: {out}")


if __name__ == "__main__":
    main()
