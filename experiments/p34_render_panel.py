"""Render the lab panel from a real captured segment.

Produces three artefacts per run:

  panel.png          preview, for review on the host
  panel.fb           raw /dev/fb0 bytes (800 x 480 x 4, BGRA)
  panel.fb.gz        the same bytes gzipped, which is what actually travels over
                     the serial console (1.5 MB raw is about 3 minutes; the
                     compressed panel is a few tens of KB)

The frame is built from one capture: matched-filtered constellation for the
symbol panel and a Welch PSD for the spectrum. No live streaming is implied -
this renders one snapshot.
"""

import argparse
import gzip
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from rfsig.carrier_tracking import align_rotation, constellation, evm_db, track_carrier
from rfsig.iq_io import load_iq_dma_s16
from rfsig.panel_render import (
    PANEL_HEIGHT,
    PANEL_WIDTH,
    PanelContent,
    framebuffer_bytes,
    render_panel,
    save_png,
)
from rfsig.pulse_shaping import rrc_taps
from rfsig.spectrum import welch_power_spectrum

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_RATE_HZ = 30_720_000
SPS = 128
ROLLOFF, SPAN = 0.35, 10
GUARD = 640


def moment_carrier(block, order):
    unit = block / np.maximum(np.abs(block), 1e-12)
    moment = unit ** order
    window = np.hanning(moment.size)
    size = int(2 ** np.ceil(np.log2(moment.size * 4)))
    spectrum = np.abs(np.fft.fft(moment * window, n=size))
    freqs = np.fft.fftfreq(size, d=1.0 / SAMPLE_RATE_HZ)
    index = int(np.argmax(spectrum))
    left, centre, right = (spectrum[(index - 1) % size], spectrum[index],
                           spectrum[(index + 1) % size])
    denom = left - 2 * centre + right
    delta = 0.0 if denom == 0 else 0.5 * (left - right) / denom
    return float(freqs[index] + delta * (SAMPLE_RATE_HZ / size)) / order


def demodulate(capture, modulation: str, order: int):
    carrier = moment_carrier(capture, order)
    n = np.arange(capture.size)
    baseband = capture * np.exp(-2j * np.pi * carrier * n / SAMPLE_RATE_HZ)
    filtered = np.convolve(baseband, rrc_taps(ROLLOFF, SPAN, SPS), mode="same")

    best_offset, best_power = 0, -np.inf
    for offset in range(SPS):
        segment = filtered[offset::SPS][16:-16]
        if segment.size < 32:
            continue
        power = float(np.mean(np.abs(segment) ** 2))
        if power > best_power:
            best_offset, best_power = offset, power

    symbols = filtered[best_offset::SPS]
    trim = int(np.ceil(GUARD / SPS))
    symbols = symbols[trim:-trim]

    table = constellation(modulation)
    if modulation in ("bpsk", "qpsk"):
        # Constant modulus: the M-th power collapses the constellation to one
        # phasor, and subtracting the table's own reference phase keeps the axes
        # meaningful (EXP-HW-015: without that offset QPSK lands 45 degrees off).
        unit = symbols / np.maximum(np.abs(symbols), 1e-12)
        moment_order = 2 if modulation == "bpsk" else 4
        reference = np.mean((table / np.abs(table)) ** moment_order)
        phase = (np.angle(np.mean(unit ** moment_order))
                 - np.angle(reference)) / moment_order
        symbols = symbols * np.exp(-1j * phase)
    else:
        # 16QAM is not constant modulus, so the power method is invalid. Without
        # the PLL and rotation search the constellation renders as rings instead
        # of a 4x4 grid and the panel would show a wrong picture (measured EVM
        # -14.96 dB instead of -37 dB).
        tracked = track_carrier(symbols, table, loop_bw=0.02).corrected
        symbols, _ = align_rotation(tracked, table, symmetry_deg=90.0)
    return carrier, best_offset, symbols, table


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                          # noqa: BLE001
        pass

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--segment", required=True, type=Path)
    parser.add_argument("--modulation", required=True,
                        help="bpsk, qpsk, qam16, or 'test' for the channel test pattern")
    parser.add_argument("--channels", type=int, default=4)
    parser.add_argument("--span-hz", type=float, default=2.0e6,
                        help="half-width of the spectrum view around the peak; the full "
                             "30.72 MHz span compresses a 240 kHz signal into one spike")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    out = args.output or ROOT / "results" / datetime.now(timezone.utc).strftime(
        "p34-panel-%Y%m%dT%H%M%SZ")
    out.mkdir(parents=True, exist_ok=True)

    if args.modulation == "test":
        from rfsig.panel_render import test_pattern as make_test_pattern
        image = make_test_pattern()
        save_png(image, out / "panel.png")
        raw = framebuffer_bytes(image)
        (out / "panel.fb").write_bytes(raw)
        with gzip.open(out / "panel.fb.gz", "wb") as handle:
            handle.write(raw)
        print(f"test pattern {image.size[0]}x{image.size[1]}, {len(raw):,} bytes")
        print(f"gzip {len(gzip.compress(raw, 9)):,} bytes")
        print(f"evidence: {out}")
        return 0

    capture = load_iq_dma_s16(args.segment, channels=args.channels)
    order = 2 if args.modulation == "bpsk" else 4
    carrier, timing, symbols, table = demodulate(capture, args.modulation, order)

    spectrum = welch_power_spectrum(capture, SAMPLE_RATE_HZ, nperseg=1024)
    frequency_hz = np.asarray(spectrum.frequency_hz)
    psd_linear = np.asarray(spectrum.psd)
    # The full 30.72 MHz span compresses a 240 kHz signal into a single spike, so
    # the view is zoomed around the peak by default.
    # Centre the view on the estimated carrier, not on the PSD peak: the peak can
    # sit at a spurious line and the axis then reads as an asymmetrical span. The
    # axis is reported relative to the carrier so 0 means "on channel".
    if args.span_hz > 0:
        keep = np.abs(frequency_hz - carrier) <= args.span_hz
        if np.count_nonzero(keep) >= 2:
            frequency_hz = frequency_hz[keep] - carrier
            psd_linear = psd_linear[keep]
    psd_db = 10 * np.log10(np.maximum(psd_linear, 1e-30))

    magnitudes = np.abs(symbols)
    in_phase = float(np.mean(symbols.real ** 2))
    quadrature = float(np.mean(symbols.imag ** 2))
    quad_db = 10 * np.log10(max(in_phase, 1e-12) / max(quadrature, 1e-12))
    evm = evm_db(symbols, table)
    cv = float(np.std(magnitudes) / max(np.mean(magnitudes), 1e-12))

    content = PanelContent(
        frequency_hz=frequency_hz,
        psd_db=psd_db,
        symbols=symbols,
        subtitle=f"{args.segment.parent.name} / {args.modulation}",
        metrics=(
            ("EVM", f"{evm:+.2f} dB"),
            ("carrier", f"{carrier / 1e3:,.1f} kHz"),
            ("symbols", f"{symbols.size}"),
            ("quad suppr", f"{quad_db:+.2f} dB"),
            ("amplitude CV", f"{cv:.4f}"),
            ("timing", f"{timing} samples"),
            ("frames", f"{capture.size:,}"),
            ("geometry", f"{PANEL_WIDTH}x{PANEL_HEIGHT} bgra32"),
        ),
    )
    image = render_panel(content)
    save_png(image, out / "panel.png")

    raw = framebuffer_bytes(image)
    (out / "panel.fb").write_bytes(raw)
    compressed = gzip.compress(raw, 9)
    (out / "panel.fb.gz").write_bytes(compressed)

    report = {
        "schema": "rfsig.panel_render.v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "segment": str(args.segment),
        "modulation": args.modulation,
        "carrier_hz": round(carrier, 2),
        "timing_offset": int(timing),
        "symbols": int(symbols.size),
        "evm_db": round(evm, 3),
        "quadrature_suppression_db": round(quad_db, 3),
        "amplitude_cv": round(cv, 4),
        "panel_pixels": [PANEL_WIDTH, PANEL_HEIGHT],
        "framebuffer_bytes": len(raw),
        "gzip_bytes": len(compressed),
        "pixel_format": "bgra32",
        "note": ("one snapshot rendered on the host; the board only writes the bytes. "
                 "Channel order must be confirmed on the panel with the test pattern."),
    }
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                                     encoding="utf-8")

    print(f"{args.modulation}: carrier {carrier:,.1f} Hz, {symbols.size} symbols, "
          f"EVM {evm:+.2f} dB")
    print(f"panel {PANEL_WIDTH}x{PANEL_HEIGHT} bgra32: {len(raw):,} bytes, "
          f"gzip {len(compressed):,} bytes")
    print(f"evidence: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
