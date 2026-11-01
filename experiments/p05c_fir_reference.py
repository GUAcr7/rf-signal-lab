"""Verify a fixed offline FIR against theory and existing P04 files; never RX/TX."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from time import perf_counter

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from rfsig.fir import FirStream, apply_fir_full, design_lowpass_fir


ROOT = Path(__file__).resolve().parents[1]
FS, PASS_EDGE, STOP_EDGE, CUTOFF, TAPS = 1_000_000, 100_000, 200_000, 150_000, 63
MAX_PASS_DEVIATION_DB, MAX_PASS_RIPPLE_DB, MIN_STOP_ATTENUATION_DB = .1, .1, 50.
MAX_WAVEFORM_NRMSE = .01
SOURCE_RECORDS = {
    "BPSK": "p04-bpsk-20261003T102947621995Z",
    "QPSK": "p04-qpsk-20261003T103128391971Z",
    "16QAM": "p04-16qam-20261003T103357180550Z",
}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def direct_response(taps, frequencies):
    return np.exp(-2j*np.pi*np.asarray(frequencies)[:, None]*np.arange(len(taps))/FS) @ taps


def explicit_convolution(iq, taps):
    """Separate shift-and-add oracle, not np.convolve or the streaming routine."""
    output = np.zeros(len(iq)+len(taps)-1, dtype=np.complex128)
    for k, coefficient in enumerate(taps):
        output[k:k+len(iq)] += coefficient*iq
    return output


def block_reference(iq, taps):
    stream = FirStream(taps)
    chunks, start, pattern = [], 0, (1, 7, 127, 1024, 3, 4096)
    sizes = []
    while start < len(iq):
        size = min(pattern[len(sizes) % len(pattern)], len(iq)-start)
        chunks.append(stream.process(iq[start:start+size]))
        sizes.append(size)
        start += size
    chunks.append(stream.finish())
    return np.concatenate(chunks), sizes


def main():
    # Fixed thresholds above are specified before testing, not fitted to results.
    taps = design_lowpass_fir(FS, CUTOFF, TAPS)
    delay = (TAPS-1)//2
    nfft = 262144
    frequency = np.fft.rfftfreq(nfft, 1/FS)
    response = np.fft.rfft(taps, nfft)
    edge_frequency = np.array([0., 84375., PASS_EDGE, CUTOFF, STOP_EDGE, FS/2])
    edge_response = direct_response(taps, edge_frequency)
    # Include exact edges even when an FFT grid does not land on them.
    f = np.concatenate((frequency, edge_frequency))
    h = np.concatenate((response, edge_response))
    db = 20*np.log10(np.maximum(np.abs(h), 1e-300))
    pass_db, stop_db = db[f <= PASS_EDGE], db[f >= STOP_EDGE]
    pass_deviation = float(np.max(np.abs(pass_db)))
    pass_ripple = float(np.max(pass_db)-np.min(pass_db))
    stop_attenuation = float(-np.max(stop_db))
    assert pass_deviation <= MAX_PASS_DEVIATION_DB
    assert pass_ripple <= MAX_PASS_RIPPLE_DB
    assert stop_attenuation >= MIN_STOP_ATTENUATION_DB
    indices = np.unique(np.rint(np.linspace(0,len(frequency)-1,513)).astype(int))
    np.testing.assert_allclose(response[indices],direct_response(taps,frequency[indices]),atol=3e-14,rtol=1e-12)
    np.testing.assert_allclose(direct_response(taps,-edge_frequency),np.conj(edge_response),atol=3e-14,rtol=0)

    arrays = {"taps":taps, "response_frequency_hz":frequency, "response":response,
              "exact_edge_frequency_hz":edge_frequency, "exact_edge_response":edge_response}
    tones = []
    time_index = np.arange(8192)
    for tone in (50000., -50000., 300000., -300000.):
        x = (.7+.2j)*np.exp(2j*np.pi*tone*time_index/FS)
        y = apply_fir_full(x,taps)
        analytic = direct_response(taps,[tone])[0]
        stable = slice(TAPS-1,len(x))
        expected = x[stable]*analytic
        np.testing.assert_allclose(y[stable],expected,atol=2e-12,rtol=1e-9)
        measured = np.vdot(x[stable],y[stable])/np.vdot(x[stable],x[stable])
        power_ratio = float(np.mean(abs(y[stable])**2)/np.mean(abs(x[stable])**2))
        np.testing.assert_allclose(power_ratio,abs(analytic)**2,atol=1e-14,rtol=1e-9)
        tones.append({"frequency_hz":tone,"analytic_gain_real":float(analytic.real),
                      "analytic_gain_imag":float(analytic.imag),
                      "measured_gain_real":float(measured.real),"measured_gain_imag":float(measured.imag),
                      "amplitude_gain_db":float(20*np.log10(abs(measured))),
                      "power_ratio":power_ratio,
                      "max_steady_sample_error":float(np.max(abs(y[stable]-expected))),
                      "steady_output_index_range":[TAPS-1,len(x)-1]})

    reports, source_hashes = [], {}
    for label,directory in SOURCE_RECORDS.items():
        source = ROOT/"results"/directory
        meta = json.loads((source/"metadata.json").read_text(encoding="utf-8"))
        assert meta["source"] == "python_simulation_not_rf_capture"
        assert meta["modulation"] == label and meta["sample_rate_hz"] == FS
        assert meta["symbol_rate_hz"] == 125000 and meta["rolloff"] == .35
        assert sha256(source/"reference.npz") == meta["npz_sha256"]
        source_hashes[directory] = {name:sha256(source/name) for name in ("reference.npz","metadata.json")}
        with np.load(source/"reference.npz",allow_pickle=False) as saved:
            x = saved["shaped_iq"].copy()
        y = apply_fir_full(x,taps)
        explicit = explicit_convolution(x,taps)
        np.testing.assert_allclose(y,explicit,atol=5e-14,rtol=5e-14)
        blocked,sizes = block_reference(x,taps)
        np.testing.assert_allclose(blocked,y,atol=5e-14,rtol=5e-14)
        aligned = y[delay:delay+len(x)]
        nrmse = float(np.sqrt(np.sum(abs(aligned-x)**2)/np.sum(abs(x)**2)))
        assert nrmse <= MAX_WAVEFORM_NRMSE
        assert len(y) == len(x)+TAPS-1
        tag = label.lower()
        arrays.update({tag+"_input":x,tag+"_output_full":y,tag+"_output_aligned":aligned,
                       tag+"_output_blocks_with_tail":blocked})
        reports.append({"modulation":label,"source_record":str(source.relative_to(ROOT)),
                        "input_count":len(x),"full_output_count":len(y),
                        "relative_waveform_rms_error":nrmse,
                        "input_mean_power":float(np.mean(abs(x)**2)),
                        "aligned_output_mean_power":float(np.mean(abs(aligned)**2)),
                        "explicit_convolution_max_error":float(np.max(abs(y-explicit))),
                        "streaming_with_tail_max_error":float(np.max(abs(blocked-y))),
                        "block_sizes":sizes,"passed":True})

    # Keep source and interferer components separate to avoid misreading a
    # fall in total mixture power as improved target power or measured SNR.
    target = arrays["qpsk_input"]
    n = np.arange(len(target))
    interferer = .5*np.exp(2j*np.pi*300000*n/FS)
    mix = target+interferer
    mixture_output = apply_fir_full(mix,taps)
    interferer_output = apply_fir_full(interferer,taps)
    np.testing.assert_allclose(mixture_output,arrays["qpsk_output_full"]+interferer_output,atol=5e-14,rtol=5e-14)
    stable = slice(TAPS-1,len(target))
    interference_gain = float(20*np.log10(np.sqrt(np.mean(abs(interferer_output[stable])**2)/np.mean(abs(interferer[stable])**2))))
    assert interference_gain <= -MIN_STOP_ATTENUATION_DB
    arrays.update(mixture_input=mix,mixture_output_full=mixture_output,
                  interferer_input=interferer,interferer_output_full=interferer_output)

    # Timings measure the whole host call, including validation/allocation.
    # They exclude source reads, drawing, streaming and any RF/FPGA/AI work.
    apply_fir_full(target,taps)
    timings = []
    for _ in range(20):
        started = perf_counter()
        apply_fir_full(target,taps)
        timings.append(perf_counter()-started)

    output = ROOT/"results"/datetime.now(timezone.utc).strftime("p05c-fir-%Y%m%dT%H%M%S%fZ")
    output.mkdir()
    archive = output/"reference.npz"
    np.savez_compressed(archive,**arrays)
    with np.load(archive,allow_pickle=False) as loaded:
        assert set(loaded.files) == set(arrays)
        for key,expected in arrays.items():
            np.testing.assert_array_equal(loaded[key],expected)

    fig,axes = plt.subplots(2,2,figsize=(12,8),layout="constrained")
    gain_db = 20*np.log10(np.maximum(abs(response),1e-8))
    axes[0,0].plot(frequency/1e3,gain_db)
    axes[0,0].axvspan(0,PASS_EDGE/1e3,color="green",alpha=.12)
    axes[0,0].axvspan(STOP_EDGE/1e3,FS/2000,color="orange",alpha=.12)
    axes[0,0].axhline(-50,color="red",linestyle="--",label="Stop requirement: -50 dB")
    axes[0,0].set(title="63-tap low-pass response",xlabel="Baseband frequency (kHz)",ylabel="Amplitude gain (dB)",ylim=(-110,1))
    axes[0,0].legend(fontsize=8)
    axes[0,1].plot(frequency[frequency<=PASS_EDGE]/1e3,gain_db[frequency<=PASS_EDGE])
    axes[0,1].axhline(.1,color="red",linestyle="--")
    axes[0,1].axhline(-.1,color="red",linestyle="--")
    axes[0,1].set(title="Passband: fixed +/-0.1 dB bounds",xlabel="Baseband frequency (kHz)",ylabel="Amplitude gain (dB)",ylim=(-.12,.12))
    shown = slice(500,660)
    axes[1,0].plot(n[shown]/FS*1e6,target[shown].real,label="Original QPSK I")
    axes[1,0].plot(n[shown]/FS*1e6,arrays["qpsk_output_aligned"][shown].real,linestyle="--",label="Filtered I; 31-sample alignment")
    axes[1,0].set(title="No gain/phase fitting or renormalization",xlabel="Source time (us)",ylabel="Dimensionless amplitude")
    axes[1,0].legend(fontsize=8)
    segment=slice(512,512+8192)
    weights=np.hanning(8192)
    def plot_psd(values,label):
        psd=abs(np.fft.fftshift(np.fft.fft(values[segment]*weights)))**2/(FS*np.sum(weights**2))
        axes[1,1].plot(np.fft.fftshift(np.fft.fftfreq(8192,1/FS))/1e3,
                       10*np.log10(np.maximum(psd,1e-16)),label=label)
    plot_psd(mix,"QPSK + synthetic 300 kHz tone")
    plot_psd(mixture_output[delay:delay+len(mix)],"Filtered; delay aligned")
    axes[1,1].set(title="Known synthetic interference; not RF capture",xlabel="Baseband frequency (kHz)",ylabel="PSD (dimensionless^2/Hz, dB)",ylim=(-140,-20))
    axes[1,1].legend(fontsize=8)
    for ax in axes.flat:
        ax.grid(True,alpha=.3)
    fig.suptitle("P05c OFFLINE FIR REFERENCE | Fs=1 MS/s | no board / no AI")
    fig.savefig(output/"reference.png",dpi=140)
    plt.close(fig)

    report = {
        "schema":"rfsig.p05c_fir_reference.v1","source_kind":"saved_p04_simulation_not_rf_capture",
        "created_utc":datetime.now(timezone.utc).isoformat(),
        "specification":{"sample_rate_hz":FS,"pass_edge_hz":PASS_EDGE,"stop_edge_hz":STOP_EDGE,
                         "sinc_cutoff_hz":CUTOFF,"tap_count":TAPS,"window":"symmetric Hamming",
                         "max_pass_deviation_db":MAX_PASS_DEVIATION_DB,"max_pass_ripple_db":MAX_PASS_RIPPLE_DB,
                         "min_stop_attenuation_db":MIN_STOP_ATTENUATION_DB,"max_waveform_nrmse":MAX_WAVEFORM_NRMSE},
        "measured_response":{"nfft":nfft,"positive_fft_grid_count":len(frequency),
                             "fft_grid_spacing_hz":FS/nfft,"exact_extra_edges_hz":edge_frequency.tolist(),
                             "pass_max_abs_db":pass_deviation,"pass_peak_to_peak_db":pass_ripple,
                             "stop_min_attenuation_db":stop_attenuation,
                             "dc_gain":float(np.sum(taps)),
                             "symmetry_max_error":float(np.max(abs(taps-taps[::-1]))),
                             "direct_response_max_error":float(np.max(abs(response[indices]-direct_response(taps,frequency[indices])))),
                             "scope":"dense numerical grid with exact edges; not an analytic continuous-frequency extremum proof"},
        "group_delay_samples":delay,"group_delay_seconds":delay/FS,
        "tone_checks":tones,"waveforms":reports,
        "interference_check":{"frequency_hz":300000,"input_amplitude":.5,"component_gain_db":interference_gain,
                              "scope":"known deterministic simulation, separate components; not measured SNR or RF selectivity"},
        "host_timing":{"record_input_count":len(target),"tap_count":TAPS,"warmup_calls":1,"measured_calls":20,
                       "seconds":timings,"median_seconds":float(np.median(timings)),
                       "scope":"whole-record host float FIR call including input validation and array allocation; no drawing, file I/O, RF, FPGA or AI"},
        "source_file_sha256":source_hashes,"arrays_sha256":sha256(archive),
        "source_code_sha256":{name:sha256(ROOT/name) for name in ("src/rfsig/fir.py","experiments/p05c_fir_reference.py","tests/test_fir.py")},
        "roundtrip_arrays_equal":True,"passed":True,"board_accessed":False,"rf_configuration_written":False,
        "tx_started":False,"live_receiver_filter_connected":False,"fpga_implemented":False,"ai_connected":False,
        "sample_units":"dimensionless P04 simulation; no new normalization applied",
        "limitations":"not Fs=30.72MS/s coefficients; not symbol EVM/BER/AI accuracy; no claim of RF or hardware throughput",
    }
    (output/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({"passed":True,"output":str(output),"pass_max_abs_db":pass_deviation,
                      "pass_peak_to_peak_db":pass_ripple,"stop_min_attenuation_db":stop_attenuation,
                      "waveform_nrmse":{row["modulation"]:row["relative_waveform_rms_error"] for row in reports},
                      "interferer_component_gain_db":interference_gain,
                      "host_convolution_median_ms":1000*np.median(timings)},ensure_ascii=False,indent=2))


if __name__ == "__main__":
    main()
