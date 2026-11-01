"""Analyse a captured modulated signal from the two-board link.

The receiver and transmitter use independent local oscillators, so the capture
arrives with an unknown carrier offset and an unknown sampling phase. This script
therefore estimates the centre frequency from the capture itself rather than
assuming it, then matched-filters and looks for the constellation signature the
transmitted waveform should produce:

  BPSK    two phase clusters 180 degrees apart, near-zero quadrature
  QPSK    four phase clusters 90 degrees apart, one amplitude ring
  16QAM   three amplitude rings, twelve phase angles

Nothing here decides "which modulation is this" by fiat; it reports the
statistics and lets the numbers speak. A tone is included as a control: it must
show a single amplitude ring and no phase structure.

Usage:
  python experiments/p21_analyse_mod_capture.py \
      --segment results/p21-rx-bpsk-decoded-20261017/segment.bin \
      --label bpsk --samples-per-symbol 128 --rolloff 0.35 \
      --output results/p21-bpsk-analysis
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from rfsig.bandwidth import occupied_bandwidth
from rfsig.iq_io import load_iq_dma_s16
from rfsig.pulse_shaping import rrc_taps
from rfsig.spectrum import welch_power_spectrum

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_RATE_HZ = 30_720_000
EXPECTED_OFFSET_HZ = 960_000.0


def estimate_centre(iq, sample_rate_hz, search_hz=2_000_000.0):
    """Return the frequency of the strongest PSD bin within +/- search_hz."""
    spectrum = welch_power_spectrum(iq, sample_rate_hz, nperseg=1024)
    freq = np.asarray(spectrum.frequency_hz)
    psd = np.asarray(spectrum.psd)
    mask = np.abs(freq) <= search_hz
    if not mask.any():
        raise ValueError("search band is empty")
    index = int(np.argmax(psd[mask]))
    return float(freq[mask][index]), freq, psd, spectrum


def matched_filter(iq, rolloff, span_symbols, samples_per_symbol):
    taps = rrc_taps(rolloff, span_symbols, samples_per_symbol)
    return np.convolve(iq, taps, mode="same")


def best_phase(baseband, samples_per_symbol, order):
    """Pick the decimation offset that maximises the order-th moment magnitude.

    For BPSK the 2nd moment of a properly aligned constellation is large; for
    QPSK the 4th. This finds the symbol instant without a decision-directed loop.
    """
    best_offset, best_score = 0, -np.inf
    for offset in range(samples_per_symbol):
        symbols = baseband[offset::samples_per_symbol]
        if symbols.size < 64:
            continue
        unit = symbols / np.maximum(np.abs(symbols), 1e-12)
        score = np.abs(np.mean(unit ** order))
        if score > best_score:
            best_score, best_offset = score, offset
    return best_offset, best_score


def align_carrier(symbols, order):
    """De-rotate by 1/order of the mean of unit**order. Returns symbols and phase."""
    unit = symbols / np.maximum(np.abs(symbols), 1e-12)
    moment = np.mean(unit ** order)
    phase = np.angle(moment) / order
    return symbols * np.exp(-1j * phase), float(phase)


def refine_carrier(filtered, coarse_hz, sample_rate_hz, samples_per_symbol, order,
                   search_hz=400_000.0):
    """Measure the residual carrier precisely by removing modulation, then FFT.

    A grid search is the wrong tool on a long block: 65,536 samples span 2.13 ms,
    so the moment peak is narrower than a 500 Hz step and the search just walks to
    the edge of its window (that is exactly what happened here - it reported
    -206 kHz against a +/-200 kHz window). Raising the modulation to the order-th
    power collapses the constellation to a single tone at order x carrier offset,
    whose frequency can then be read off an FFT peak with parabolic interpolation.
    """
    n = np.arange(filtered.size)
    unit = filtered / np.maximum(np.abs(filtered), 1e-12)
    moment = unit ** order
    window = np.hanning(moment.size)
    size = int(2 ** np.ceil(np.log2(moment.size * 4)))
    spectrum = np.abs(np.fft.fft(moment * window, n=size))
    freqs = np.fft.fftfreq(size, d=1.0 / sample_rate_hz)

    limit = search_hz * order
    allowed = np.abs(freqs) <= limit
    if not allowed.any():
        raise ValueError("moment search band is empty")
    index = int(np.argmax(np.where(allowed, spectrum, -np.inf)))

    # Parabolic interpolation on the magnitude peak, handling wrap-around.
    left = spectrum[(index - 1) % size]
    centre = spectrum[index]
    right = spectrum[(index + 1) % size]
    denominator = left - 2 * centre + right
    delta = 0.0 if denominator == 0 else 0.5 * (left - right) / denominator
    bin_width = sample_rate_hz / size
    moment_hz = freqs[index] + delta * bin_width

    residual = moment_hz / order
    shifted = filtered * np.exp(-2j * np.pi * residual * n / sample_rate_hz)
    offset, score = best_phase(shifted, samples_per_symbol, order)
    return {
        "score": float(score),
        "hz": float(coarse_hz + residual),
        "residual_hz": float(residual),
        "offset": int(offset),
        "filtered": shifted,
        "moment_snr_db": float(10 * np.log10(
            (centre ** 2) / max(np.mean(spectrum[allowed] ** 2), 1e-30))),
    }

def ring_metrics(magnitudes):
    """Count distinct amplitude rings by looking for separated histogram peaks."""
    if magnitudes.size == 0:
        return {"rings": 0}
    lo, hi = float(np.percentile(magnitudes, 2)), float(np.percentile(magnitudes, 98))
    if hi <= lo:
        return {"rings": 1, "spread_ratio": 1.0}
    counts, edges = np.histogram(magnitudes, bins=40, range=(lo, hi))
    smooth = np.convolve(counts, [1, 2, 3, 2, 1], mode="same")
    peaks = []
    for i in range(1, len(smooth) - 1):
        if smooth[i] > smooth[i - 1] and smooth[i] >= smooth[i + 1]:
            if smooth[i] > 0.15 * smooth.max():
                peaks.append(float((edges[i] + edges[i + 1]) / 2))
    merged = []
    for value in peaks:
        if not merged or abs(value - merged[-1]) > 0.18 * (hi - lo):
            merged.append(value)
    return {
        "rings": len(merged),
        "ring_positions": [round(v / max(merged[-1], 1e-12), 3) for v in merged],
        "spread_ratio": round(hi / max(lo, 1e-12), 3),
    }


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                          # noqa: BLE001
        pass

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--segment", required=True, type=Path)
    parser.add_argument("--dma-buffer-samples",required=True,type=int,
                        help="recorded buffer size; rejects a joined multi-buffer input")
    parser.add_argument("--label", required=True)
    parser.add_argument("--channels", type=int, default=4)
    parser.add_argument("--samples-per-symbol", type=int, default=128)
    parser.add_argument("--rolloff", type=float, default=0.35)
    parser.add_argument("--span-symbols", type=int, default=10)
    parser.add_argument("--moment-order", type=int, default=2,
                        help="2 for BPSK/tone, 4 for QPSK, 2 or 4 for 16QAM")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    iq = load_iq_dma_s16(args.segment, channels=args.channels)
    if args.dma_buffer_samples<=0 or len(iq)>args.dma_buffer_samples:
        parser.error("multi-buffer capture may have time gaps; use p22 diagnostics or split at DMA boundaries")
    if iq.size < 4096:
        print("segment too short")
        return 2

    centre, freq, psd, spectrum = estimate_centre(iq, SAMPLE_RATE_HZ)

    obw = occupied_bandwidth(
        frequency_hz=freq,
        psd=psd,
        analysis_band_hz=(-14_000_000.0, 14_000_000.0),
        occupied_fraction=0.99,
    )

    n = np.arange(iq.size)
    baseband = iq * np.exp(-2j * np.pi * centre * n / SAMPLE_RATE_HZ)
    filtered = matched_filter(baseband, args.rolloff, args.span_symbols,
                              args.samples_per_symbol)
    refined = refine_carrier(filtered, centre, SAMPLE_RATE_HZ,
                             args.samples_per_symbol, args.moment_order)
    filtered = refined["filtered"]
    centre = refined["hz"]
    offset = refined["offset"]
    symbols = filtered[offset::args.samples_per_symbol]
    symbols, carrier_phase = align_carrier(symbols, args.moment_order)

    mags = np.abs(symbols)
    rings = ring_metrics(mags)
    phase_deg = np.degrees(np.angle(symbols))

    # Quadrature suppression: how much of the energy sits on the in-phase axis.
    in_phase = float(np.mean(np.abs(symbols.real)) ** 2)
    quadrature = float(np.mean(np.abs(symbols.imag)) ** 2)
    quad_suppression_db = 10 * np.log10(max(in_phase, 1e-12) / max(quadrature, 1e-12))

    hist, edges = np.histogram(phase_deg, bins=36, range=(-180, 180))
    top = np.argsort(hist)[::-1][:4]
    clusters = sorted(round(float((edges[i] + edges[i + 1]) / 2), 1) for i in top if hist[i] > 0.05 * hist.sum())

    report = {
        "schema": "rfsig.mod_capture_analysis.v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "label": args.label,
        "segment": str(args.segment),
        "samples": int(iq.size),
        "estimated_centre_hz": round(centre, 1),
        "expected_offset_hz": EXPECTED_OFFSET_HZ,
        "offset_error_hz": round(centre - EXPECTED_OFFSET_HZ, 1),
        "occupied_bandwidth_hz": obw.bandwidth_hz,
        "occupied_bandwidth_status": obw.status,
        "occupied_centre_baseband_hz": obw.center_baseband_hz,
        "symbols_analysed": int(symbols.size),
        "timing_offset_samples": int(offset),
        "residual_carrier_hz": round(refined.get("residual_hz", 0.0), 1),
        "moment_snr_db": round(refined.get("moment_snr_db", 0.0), 2),
        "carrier_phase_deg": round(np.degrees(carrier_phase), 2),
        "rms_amplitude": round(float(np.sqrt(np.mean(mags ** 2))), 2),
        "quadrature_suppression_db": round(quad_suppression_db, 2),
        "phase_clusters_deg": clusters,
        "rings": rings,
        "magnitude_cv": round(float(np.std(mags) / max(np.mean(mags), 1e-12)), 4),
    }

    print(f"label                  : {args.label}")
    print(f"samples                : {iq.size:,}")
    print(f"estimated centre       : {centre:,.1f} Hz  (expected {EXPECTED_OFFSET_HZ:,.0f}, "
          f"error {centre - EXPECTED_OFFSET_HZ:+,.1f})")
    print(f"timing offset          : {offset} samples")
    print(f"carrier phase          : {np.degrees(carrier_phase):+.2f} deg")
    print(f"symbols                : {symbols.size:,}")
    print(f"quadrature suppression : {quad_suppression_db:+.2f} dB"
          f"  (BPSK high, QPSK/16QAM low by construction)")
    print(f"phase clusters (deg)   : {clusters}")
    print(f"amplitude CV           : {report['magnitude_cv']:.4f}"
          f"  (single ring ~0.1, 16QAM multi-ring higher)")
    print(f"amplitude rings        : {rings['rings']}  positions {rings.get('ring_positions')}")

    out = args.output or ROOT / "results" / datetime.now(timezone.utc).strftime(
        "p21-analysis-%Y%m%dT%H%M%SZ")
    out.mkdir(parents=True, exist_ok=True)
    (out / "analysis.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                                       encoding="utf-8")
    np.save(out / "symbols.npy", symbols)
    print(f"\nevidence: {out / 'analysis.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
