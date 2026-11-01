"""Draw 64 samples of a 1 kHz cosine. Run with the project Python environment."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # Save a figure without requiring a desktop GUI backend.
import matplotlib.pyplot as plt
import numpy as np

from rfsig.sampling import sample_cosine


def main() -> None:
    frequency_hz = 1_000.0
    sample_rate_hz = 16_000.0
    num_samples = 64
    times_s, samples = sample_cosine(frequency_hz, sample_rate_hz, num_samples)

    # This dense curve illustrates the mathematical waveform, not extra samples.
    illustration_times_s = np.linspace(0, num_samples / sample_rate_hz, 1_001)
    illustration = np.cos(2 * np.pi * frequency_hz * illustration_times_s)
    fig, ax = plt.subplots(figsize=(10, 4.5), layout="constrained")
    ax.plot(illustration_times_s * 1_000, illustration, color="#a6b4c5",
            linewidth=1.5, label="Mathematical waveform (illustration)")
    ax.plot(times_s * 1_000, samples, "o", color="#087f8c", markersize=5,
            label="64 stored samples")
    ax.set(title="Sampling: 1 kHz cosine at 16,000 samples/s",
           xlabel="Time (ms)", ylabel="Amplitude (dimensionless)",
           xlim=(0, 4), ylim=(-1.25, 1.25))
    ax.set_xticks(np.arange(0, 4.01, 0.5))
    ax.grid(alpha=0.2)
    ax.legend(loc="upper right", fontsize=8)
    output = Path(__file__).resolve().parents[1] / "results" / "level0_sampling.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=160)
    plt.close(fig)

    print(f"Frequency: {frequency_hz:g} Hz")
    print(f"Sample rate: {sample_rate_hz:g} samples/s")
    print(f"Sample interval: {1e6 / sample_rate_hz:g} us")
    print(f"Samples per cycle: {sample_rate_hz / frequency_hz:g}")
    print(f"Samples: {len(samples)}; last sample time: {times_s[-1] * 1e3:g} ms")
    print("Samples at n=0,4,8,12,16:", np.round(samples[[0, 4, 8, 12, 16]], 6))
    print(f"Figure: {output}")


if __name__ == "__main__":
    main()
