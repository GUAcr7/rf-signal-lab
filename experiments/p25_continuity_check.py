"""Check modulo source-position consistency of multi-buffer captures.

Question: yesterday a `-b 4096 -s 65536` capture contained 12 source-time jumps,
while a single `-b 65536 -s 65536` buffer had none. That says nothing about what
happens when TWO large buffers are concatenated, which is what a long capture
would do. This measures it directly.

Method: every buffer-sized window of the capture is aligned against the known
transmitted waveform, giving its source position. Consecutive positions should
advance by one buffer, within integer-delay tolerance. Strong adjacent matches
can expose non-periodic jumps, but losses of a whole source period are invisible.
No output from this periodic-reference method proves lossless capture.

Control: the same code is run on yesterday's `-b 4096` file, where 12 gaps are
already established (EXP-HW-014). If this code does not reproduce ~12 there, it
cannot be trusted on the new data.
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timezone

import numpy as np

from rfsig.capture_continuity import align_periodic_reference, assess_source_progress
from rfsig.iq_io import load_iq_dma_s16

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_RATE_HZ = 30_720_000
PERIOD = 131_072
SPS = 128
ROLLOFF, SPAN, SEED, PEAK = 0.35, 10, 20261016, 256
NOMINAL_OFFSET_HZ = 960_000.0


def reference_samples() -> np.ndarray:
    from rfsig.tx_waveforms import make_tx_waveform, pack_tx_iq_le16
    waveform = make_tx_waveform(
        "BPSK", sample_rate_hz=SAMPLE_RATE_HZ, samples_per_symbol=SPS,
        symbol_count=PERIOD // SPS, seed=SEED, offset_hz=960_000.0,
        digital_peak_counts=PEAK, rolloff=ROLLOFF, span_symbols=SPAN,
    )
    words = np.frombuffer(pack_tx_iq_le16(waveform.iq), dtype="<i2").astype(np.float64)
    passband = words[0::2] + 1j * words[1::2]
    # align_periodic_reference wants a BASEBAND reference. Handing it the
    # passband waveform leaves the 960 kHz offset on one side only, and the
    # correlation collapses to noise (measured: 0.004 with nmse +48 dB, versus
    # 0.998 and -25 dB once the reference is downconverted).
    index = np.arange(passband.size)
    return passband * np.exp(-2j * np.pi * NOMINAL_OFFSET_HZ * index / SAMPLE_RATE_HZ)


def initial_frequency(capture: np.ndarray) -> float:
    unit = capture / np.maximum(np.abs(capture), 1e-12)
    moment = unit ** 2
    window = np.hanning(moment.size)
    size = int(2 ** np.ceil(np.log2(moment.size * 4)))
    spectrum = np.abs(np.fft.fft(moment * window, n=size))
    freqs = np.fft.fftfreq(size, d=1.0 / SAMPLE_RATE_HZ)
    index = int(np.argmax(spectrum))
    left, centre, right = (spectrum[(index - 1) % size], spectrum[index],
                           spectrum[(index + 1) % size])
    denom = left - 2 * centre + right
    delta = 0.0 if denom == 0 else 0.5 * (left - right) / denom
    return float(freqs[index] + delta * (SAMPLE_RATE_HZ / size)) / 2


def check(path: Path, buffer_samples: int, reference: np.ndarray,
          max_refine_hz: float = 5_000.0) -> dict:
    capture = load_iq_dma_s16(path, channels=4)
    if capture.size == 0 or capture.size % buffer_samples:
        raise ValueError("capture must contain nonempty whole DMA buffers")
    windows = capture.size // buffer_samples
    starts, correlations, nmse, errors, frequencies = [], [], [], [], []
    for index in range(windows):
        window = capture[index * buffer_samples:(index + 1) * buffer_samples]
        # Estimate the carrier from this window alone. Carrying one fit forward
        # across a gap mixes two different source segments and was what made 14
        # of 16 control windows fail to align.
        try:
            frequency = initial_frequency(window)
            fit = align_periodic_reference(window, reference, SAMPLE_RATE_HZ, frequency,
                                           max_refine_hz=max_refine_hz)
        except ValueError as exc:
            # Failed matching is unverified; it can also be caused by noise,
            # wrong settings or reference. It is not proof of a sample jump.
            errors.append({"window": index, "error": str(exc)})
            starts.append(None)
            correlations.append(None)
            nmse.append(None)
            frequencies.append(None)
            continue
        starts.append(fit.source_start)
        correlations.append(round(fit.correlation, 6))
        nmse.append(round(fit.nmse_db, 2))
        frequencies.append(round(fit.frequency_hz, 1))

    assessment = assess_source_progress(starts, correlations, buffer_samples, len(reference))
    gaps = [row["extra_advance_modulo_period"] for row in assessment["boundaries"]]
    return {
        "path": str(path.resolve()),
        "buffer_samples": buffer_samples,
        "windows": windows,
        "source_starts": starts,
        "correlations": correlations,
        "nmse_db": nmse,
        "alignment_errors": errors,
        "frequencies_hz": frequencies,
        "signed_modulo_gaps": gaps,
        "assessment": assessment,
        "cells_with_abs_gap_gt_1": assessment["detected_jump_count"],
    }


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                          # noqa: BLE001
        pass

    reference = reference_samples()
    cases = [
        ("CONTROL b-b 4096 (12 gaps known)", ROOT / "results/p22-transfer-20261017T131327Z/small.bin", 4096),
        ("TODAY   -b 65536, 2 buffers", ROOT / "results/p25-rx-2buf-raw/two.bin", 65536),
    ]

    results = []
    for label, path, buffer_samples in cases:
        if not path.is_file():
            print(f"SKIP {label}: {path} missing")
            continue
        row = check(path, buffer_samples, reference)
        row["label"] = label
        results.append(row)
        print(f"{label}")
        corrs = [c for c in row["correlations"] if c is not None]
        nm = [n for n in row["nmse_db"] if n is not None]
        print(f"  buffer {row['buffer_samples']}, windows {row['windows']}, "
              f"aligned {len(corrs)}/{row['windows']}")
        print(f"  source starts : {row['source_starts']}")
        print(f"  signed modulo : {row['signed_modulo_gaps']}")
        print(f"  status        : {row['assessment']['status']}; lossless capture unproven")
        print(f"  |gap|>1 cells : {row['cells_with_abs_gap_gt_1']}")
        if corrs:
            print(f"  correlation   : min {min(corrs):.6f}  nmse max {max(nm):.2f} dB")
        if row["alignment_errors"]:
            print(f"  failed windows: {[e['window'] for e in row['alignment_errors']]}")
        print()

    out = ROOT / "results" / datetime.now(timezone.utc).strftime("p26-continuity-recheck-%Y%m%dT%H%M%SZ")
    out.mkdir(parents=True, exist_ok=False)
    (out / "continuity.json").write_text(
        json.dumps({"schema": "rfsig.continuity_check.v2", "cases": results},
                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"evidence: {out / 'continuity.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
