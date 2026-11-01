"""Generate an offline modulation reference, plot and replay it; never TX."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from rfsig.bpsk import map_bpsk
from rfsig.modulation import map_qpsk, map_qam16
from rfsig.pulse_shaping import hold_symbols, normalize_mean_power, rrc_taps, shape_symbols


ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--modulation", choices=["BPSK", "QPSK", "16QAM"], default="BPSK")
    parser.add_argument("--seed", type=int, default=20261003)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    fs, sps, beta, span, count = 1_000_000, 8, .35, 10, 2048
    bits_per_symbol = {"BPSK":1, "QPSK":2, "16QAM":4}[args.modulation]
    bits = np.random.default_rng(args.seed).integers(0, 2, count*bits_per_symbol, dtype=np.uint8)
    mapper = {"BPSK":map_bpsk, "QPSK":map_qpsk, "16QAM":map_qam16}[args.modulation]
    symbols = mapper(bits).astype(np.complex128)
    held = hold_symbols(symbols, sps)
    taps = rrc_taps(beta, span, sps)
    raw = shape_symbols(symbols, taps, sps)
    iq, scale = normalize_mean_power(raw)
    matched = np.convolve(raw, taps[::-1])
    recovered = matched[len(taps)-1 + np.arange(count)*sps]
    if args.modulation == "BPSK":
        decisions = (recovered.real < 0).astype(np.uint8)
    elif args.modulation == "QPSK":
        decisions = np.column_stack((recovered.real < 0, recovered.imag < 0)).ravel().astype(np.uint8)
    else:
        # Only a noiseless reference self-check, not a synchronized RF demodulator.
        levels = np.array([-3.,-1.,1.,3.]) / np.sqrt(10)
        labels = np.array([[0,0],[0,1],[1,1],[1,0]],dtype=np.uint8)
        i_index = np.argmin(np.abs(recovered.real[:,None]-levels),axis=1)
        q_index = np.argmin(np.abs(recovered.imag[:,None]-levels),axis=1)
        decisions = np.column_stack((labels[i_index],labels[q_index])).ravel()
    errors = int(np.count_nonzero(decisions != bits))
    if errors:
        raise RuntimeError(f"Noiseless reference bit decisions failed: {errors}")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = args.output or ROOT / "results" / f"p04-{args.modulation.lower()}-{stamp}"
    output.mkdir(parents=True, exist_ok=False)
    vector_path = output / "reference.npz"
    np.savez(vector_path, bits=bits, symbols=symbols, held_iq=held, rrc_taps=taps, shaped_iq=iq)
    with np.load(vector_path, allow_pickle=False) as saved:
        for key, expected in {"bits":bits, "symbols":symbols, "held_iq":held,
                              "rrc_taps":taps, "shaped_iq":iq}.items():
            np.testing.assert_array_equal(saved[key], expected)

    window = np.hanning(len(iq))
    frequency = np.fft.fftshift(np.fft.fftfreq(len(iq), 1/fs))
    spectrum = np.fft.fftshift(np.fft.fft(iq*window)) / window.sum()
    fig, axes = plt.subplots(2,2,figsize=(12,8),layout="constrained")
    shown = min(160,len(held))
    axes[0,0].step(np.arange(shown)/fs*1e6, held[:shown].real, where="post", label="I")
    axes[0,0].plot(np.arange(shown)/fs*1e6, held[:shown].imag, label="Q")
    axes[0,0].set(title="Rectangular hold (teaching reference)",xlabel="Time (us)",ylabel="Normalized amplitude")
    axes[0,0].legend()
    axes[0,1].plot(np.arange(shown)/fs*1e6,iq[:shown].real,label="I")
    axes[0,1].plot(np.arange(shown)/fs*1e6,iq[:shown].imag,label="Q")
    axes[0,1].set(title="RRC-shaped IQ (includes initial transient)",xlabel="Time (us)",ylabel="Normalized amplitude")
    axes[0,1].legend()
    axes[1,0].scatter(symbols.real,symbols.imag,s=12)
    axes[1,0].set(title=f"{args.modulation} ideal symbols, before shaping",xlabel="I",ylabel="Q",xlim=(-1.6,1.6),ylim=(-1.6,1.6))
    axes[1,0].set_aspect("equal", adjustable="box")
    axes[1,1].plot(frequency/1e3,20*np.log10(np.maximum(np.abs(spectrum),1e-12)))
    half_width = (1+beta)*(fs/sps)/2
    for edge in (-half_width,half_width):
        axes[1,1].axvline(edge/1e3,color="orange",linestyle="--")
    axes[1,1].set(title="Windowed FFT; dashed: ideal RRC support",xlabel="Baseband frequency (kHz)",ylabel="Amplitude dB (normalized units)",xlim=(-250,250),ylim=(-100,0))
    for axis in axes.flat:
        axis.grid(True,alpha=.3)
    fig.suptitle(f"OFFLINE {args.modulation} | fs=1 MS/s, Rs=125 ksym/s, beta=0.35")
    fig.savefig(output/"reference.png",dpi=140)
    plt.close(fig)
    report = {
        "source":"python_simulation_not_rf_capture", "modulation":args.modulation,
        "seed":args.seed, "symbol_count":count, "bit_count":len(bits),
        "sample_rate_hz":fs, "symbol_rate_hz":fs/sps, "samples_per_symbol":sps,
        "rolloff":beta, "span_symbols":span, "tap_count":len(taps),
        "group_delay_samples":(len(taps)-1)//2, "shaped_sample_count":len(iq),
        "theoretical_sample_count":(count-1)*sps+len(taps),
        "ideal_rrc_support_total_hz":2*half_width,
        "symbol_mean_power":float(np.mean(np.abs(symbols)**2)),
        "shaped_mean_power":float(np.mean(np.abs(iq)**2)),
        "normalization_scale":scale, "rrc_energy":float(np.sum(taps**2)),
        "noiseless_matched_symbol_max_error":float(np.max(np.abs(recovered-symbols))),
        "noiseless_decision_errors":errors, "roundtrip_arrays_equal":True,
        "npz_sha256":hashlib.sha256(vector_path.read_bytes()).hexdigest(),
        "units":"dimensionless; not ADC counts, watts or dBm", "safe_direct_tx_input":False,
        "snr_db":None, "snr_note":"No noise added; no RF SNR measured",
        "limitations":"Full transient tails preserved; not cyclic TX-ready; not a dataset split or trained AI model",
    }
    (output/"metadata.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False,indent=2))
    print("Output:",output)


if __name__ == "__main__":
    main()
