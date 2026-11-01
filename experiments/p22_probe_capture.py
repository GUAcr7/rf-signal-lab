"""Offline forensic probe. Reads archived samples; never opens a device."""
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

from rfsig.iq_io import load_iq_dma_s16
from rfsig.pulse_shaping import rrc_taps

ROOT = Path(__file__).resolve().parents[1]
FS = 30_720_000


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    taps = rrc_taps(.35, 10, 128)
    for name, order in (("bpsk", 2), ("qpsk", 4), ("qam16", 4)):
        path = ROOT / f"results/p21-rx-{name}-long-decoded/segment.bin"
        x = load_iq_dma_s16(path, channels=4)
        unit = x / np.maximum(np.abs(x), 1e-12)
        size = 4 * len(x)
        fft = np.abs(np.fft.fft(unit**order * np.hanning(len(x)), n=size))
        f = np.fft.fftfreq(size, 1/FS) / order
        # A known-source diagnostic: resolve moment aliases near nominal offset.
        peak = np.argmax(np.where(abs(f-960000) < 150000, fft, -1))
        a,b,c = fft[peak-1:peak+2]
        carrier = f[peak] + .5*(a-c)/(a-2*b+c)*FS/size/order
        bb = x * np.exp(-2j*np.pi*carrier*np.arange(len(x))/FS)
        filtered = np.convolve(bb, taps, "same")
        rows = []
        for start in range(0, len(x), 8192):
            v = filtered[start:start+8192]
            # Crop filter transients, including at internal diagnostic edges.
            powers = [np.mean(abs(v[p+640:-640:128])**2) for p in range(128)]
            offset = int(np.argmax(powers))
            sy = v[offset+640:-640:128]
            phi = np.angle(np.sum(sy**order))/order
            sy *= np.exp(-1j*phi)
            rows.append({"block":start//8192, "timing":offset,
                         "cv":round(float(np.std(abs(sy))/np.mean(abs(sy))),4),
                         "phase":round(float(phi),4),
                         "moment_coherence":round(float(abs(np.sum(sy**order))/np.sum(abs(sy)**order)),4)})
        print(name, "carrier", carrier, "rows", json.dumps(rows))
        # Moment phase in 1024-sample windows retains the time structure hidden
        # by a whole-record FFT. Print independently of any PLL or symbol decisions.
        windows = bb.reshape(-1,1024)
        moments = np.mean(windows**order, axis=1)
        phase = np.unwrap(np.angle(moments))/order
        print("window_phase_rad", np.round(phase,3).tolist())
        print("window_coherence", np.round(abs(moments)/np.mean(abs(windows)**order,axis=1),3).tolist())
        # Compare the actual DAC waveform, not a freshly guessed random stream.
        txpath = ROOT / f"results/p21-mod-waveforms-20261017T122536Z/bundle/{name}.iq16le"
        packed = np.frombuffer(txpath.read_bytes(), dtype="<i2").reshape(-1,2)
        tx = (packed[:,0].astype(float)+1j*packed[:,1])/16
        ref = tx*np.exp(-2j*np.pi*960000*np.arange(len(tx))/FS)
        corr = np.fft.ifft(np.fft.fft(bb, n=len(ref))*np.conj(np.fft.fft(ref)))
        top = np.argsort(abs(corr))[-3:][::-1]
        print("tx_waveform_correlation", [(int(k),round(float(abs(corr[k])/np.sqrt(np.sum(abs(bb)**2)*np.sum(abs(ref)**2))),4)) for k in top])
        print("source_sha256",hashlib.sha256(path.read_bytes()).hexdigest())
        if name == "bpsk":
            print("4096-sample source alignment (known-source diagnosis):")
            for start in range(0,len(x),4096):
                chunk = bb[start:start+4096]
                moment = np.mean(chunk.reshape(-1,128)**2,axis=1)
                phase = np.unwrap(np.angle(moment))/2
                slope, intercept = np.polyfit(np.arange(len(moment))*128,phase,1)
                freq = carrier+slope*FS/(2*np.pi)
                chunk = chunk*np.exp(-1j*slope*np.arange(len(chunk)))
                corr = np.fft.ifft(np.fft.fft(chunk,n=len(ref))*np.conj(np.fft.fft(ref)))
                lag = int(np.argmax(abs(corr)))
                position = (-lag)%len(ref)
                target = ref[(position+np.arange(len(chunk)))%len(ref)]
                gain = np.vdot(target,chunk)/np.vdot(target,target)
                error = np.mean(abs(chunk-gain*target)**2)/np.mean(abs(gain*target)**2)
                print(start, "ref_start",position,"freq",round(freq,1),"waveform_nmse_db",round(float(10*np.log10(error)),2))


if __name__ == "__main__":
    main()
