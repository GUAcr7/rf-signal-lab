"""Plot the known I/Q tone and its FFT without touching any RF hardware."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from rfsig.tone import complex_tone


FS = 30_720_000
N = 1024
OFFSET_HZ = 960_000
AMPLITUDE = 0.5
RESULT = Path(__file__).resolve().parents[1] / "results" / "p03-reference-tone.png"


def main() -> None:
    iq = complex_tone(FS, N, OFFSET_HZ, AMPLITUDE)
    frequency = np.fft.fftshift(np.fft.fftfreq(N, d=1 / FS))
    magnitude = np.abs(np.fft.fftshift(np.fft.fft(iq))) / N
    peak_hz = float(frequency[int(np.argmax(magnitude))])

    shown = 128
    time_us = np.arange(shown) / FS * 1e6
    fig, (wave, spectrum) = plt.subplots(2, 1, figsize=(9, 6), layout="constrained")
    wave.plot(time_us, iq.real[:shown], label="I (real)")
    wave.plot(time_us, iq.imag[:shown], label="Q (imaginary)")
    wave.set(xlabel="Time (microseconds)", ylabel="Normalized value", title="Known complex tone")
    wave.legend()
    wave.grid(True)

    spectrum.plot(frequency / 1e6, magnitude)
    spectrum.axvline(OFFSET_HZ / 1e6, color="tab:red", linestyle="--", label="Expected +0.96 MHz")
    spectrum.set(xlim=(-4, 4), xlabel="Baseband frequency (MHz)", ylabel="FFT magnitude / N")
    spectrum.legend()
    spectrum.grid(True)

    RESULT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(RESULT, dpi=150)
    plt.close(fig)

    print("采样率 Hz：", FS)
    print("帧长：", N)
    print("频谱间隔 Hz：", FS / N)
    print("理论峰值 Hz：", OFFSET_HZ)
    print("实际峰值 Hz：", peak_hz)
    print("归一化峰值幅度：", float(magnitude.max()))
    print("参考图：", RESULT)
    if peak_hz != OFFSET_HZ:
        raise RuntimeError("FFT peak differs from the known reference")


if __name__ == "__main__":
    main()
