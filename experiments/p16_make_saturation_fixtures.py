"""Generate synthetic amplitude-step captures to exercise the saturation checker.

Purpose: prove `experiments/p16_check_saturation.py` reaches the right verdict on
data where the answer is known by construction, without needing a board. Two sets
are written:

  linear/      a perfectly linear receiver: each amplitude doubling quadruples
               power, so every step must read +6.0206 dB
  compressed/  the same inputs through a soft limiter, so the upper steps must
               read noticeably less than +6.0206 dB

Format matches `iio_readdev cf-ad9361-lpc`: interleaved little-endian int16,
12-bit-scale values, I then Q.
"""

import argparse
import sys
from pathlib import Path

import numpy as np

SAMPLE_RATE_HZ = 30_720_000
SAMPLES_PER_SEGMENT = 65536
OFFSET_HZ = 960_000.0
FULL_SCALE = 2048.0
AMPLITUDES = (200.0, 400.0, 800.0, 1600.0)   # each step doubles -> power x4


def make_segment(amplitude: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = np.arange(SAMPLES_PER_SEGMENT)
    carrier = np.exp(2j * np.pi * OFFSET_HZ * n / SAMPLE_RATE_HZ)
    noise = (rng.standard_normal(SAMPLES_PER_SEGMENT)
             + 1j * rng.standard_normal(SAMPLES_PER_SEGMENT)) * 0.01
    return amplitude * carrier * (1 + 0.05 * noise)


def soft_limit(iq: np.ndarray, limit: float) -> np.ndarray:
    """A magnitude-domain soft limiter.

    Deliberately NOT `np.tanh(iq/limit)`: tanh on a complex array is the complex
    hyperbolic tangent, which neither limits the magnitude nor preserves the
    phase, and it can even inflate small-signal gain. Limiting must act on |x|.
    """
    magnitude = np.abs(iq)
    safe = np.where(magnitude == 0.0, 1.0, magnitude)
    limited = limit * np.tanh(safe / limit)
    return iq * (limited / safe)


def write_segment(path: Path, iq: np.ndarray) -> None:
    """Write a 4-channel CF-AD9361 dump: I1, Q1, I2, Q2 per frame.

    Four channels rather than two because that is what the real device produces
    (see EXP-HW-009). A fixture with a different channel count would let the
    checker's default pass a test it could never pass on real data.
    """
    i = np.rint(np.real(iq)).astype(np.int32)
    q = np.rint(np.imag(iq)).astype(np.int32)
    i = np.clip(i, -32768, 32767)
    q = np.clip(q, -32768, 32767)
    frames = np.empty((i.size, 4), dtype="<i2")
    frames[:, 0] = i.astype(np.int16)
    frames[:, 1] = q.astype(np.int16)
    frames[:, 2] = i.astype(np.int16)      # RX2 mirrors RX1 in the fixture
    frames[:, 3] = q.astype(np.int16)
    path.write_bytes(frames.tobytes())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    root = args.output
    linear_dir = root / "linear"
    compressed_dir = root / "compressed"
    for directory in (linear_dir, compressed_dir):
        directory.mkdir(parents=True, exist_ok=True)

    for index, amplitude in enumerate(AMPLITUDES):
        peak = int(amplitude)
        base = make_segment(amplitude, seed=1000 + index)
        write_segment(linear_dir / f"peak{peak}.bin", base)
        write_segment(compressed_dir / f"peak{peak}.bin", soft_limit(base, FULL_SCALE))
        print(f"  peak{peak:<5d} amplitude={amplitude:7.1f}  "
              f"written to linear/ and compressed/")

    print(f"\nfixtures: {root}")
    print(f"  step order: {', '.join('peak%d' % a for a in map(int, AMPLITUDES))}")
    print(f"  full scale: {FULL_SCALE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
