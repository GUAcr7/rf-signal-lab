"""Known-source position matching for explicitly strided DMA-prefix diagnostics.

These samples have no anti-alias filter and omit most of each DMA buffer.
They are diagnostic observations, not a bandlimited replay/PSD input or a full
continuous stream. Matching retains the raw sample coordinate and tests every
possible stride phase, instead of rounding source positions to stride units.
"""
import numpy as np

from rfsig.capture_continuity import ReferenceAlignment


class StridedReferenceMatcher:
    def __init__(self, reference, stride):
        ref=np.asarray(reference,dtype=np.complex128)
        if ref.ndim!=1 or len(ref)<32 or not np.isfinite(ref).all() or not np.any(abs(ref)):
            raise ValueError("reference must be a finite powered vector")
        if isinstance(stride,bool) or not isinstance(stride,(int,np.integer)) or stride<1 or len(ref)%stride:
            raise ValueError("stride must be a positive integer dividing the source period")
        self.reference=ref.copy()
        self.stride=int(stride)
        self.phases=np.stack([ref[offset::stride] for offset in range(stride)])
        self.ffts=np.conj(np.fft.fft(self.phases,axis=1))
        self.length=self.phases.shape[1]
        self.positions=(-np.arange(self.length))%self.length
        self.energy_prefix=np.c_[np.zeros(stride),np.cumsum(np.tile(abs(self.phases)**2,(1,2)),axis=1)]
        self._energies={}

    def align(self, samples, sample_rate_hz, initial_frequency_hz, max_refine_hz=5000):
        x=np.asarray(samples,dtype=np.complex128)
        if x.ndim!=1 or not 32<=len(x)<=self.length or not np.isfinite(x).all() or not np.any(abs(x)):
            raise ValueError("samples must be finite, powered and fit within one strided period")
        if not np.isfinite(sample_rate_hz) or sample_rate_hz<=0 or not np.isfinite(initial_frequency_hz):
            raise ValueError("invalid sample rate or frequency")
        if not np.isfinite(max_refine_hz) or max_refine_hz<=0:
            raise ValueError("invalid frequency refinement interval")
        if len(x) not in self._energies:
            self._energies[len(x)]=self.energy_prefix[:,self.positions+len(x)]-self.energy_prefix[:,self.positions]
        energies=self._energies[len(x)]
        offsets=np.arange(len(x))*self.stride
        times=offsets/sample_rate_hz
        frequency=float(initial_frequency_hz)
        def match(freq):
            base=x*np.exp(-2j*np.pi*freq*times)
            fft=np.fft.fft(base,n=self.length)
            cross=np.fft.ifft(fft[None,:]*self.ffts,axis=1)
            scores=abs(cross)/np.sqrt(np.maximum(energies*np.sum(abs(x)**2),1e-30))
            phase,peak=np.unravel_index(np.argmax(scores),scores.shape)
            start=int(phase+self.stride*self.positions[peak])
            target=self.reference[(start+offsets)%len(self.reference)]
            return base,target,start,float(scores[phase,peak])
        for _ in range(4):
            base,target,_,_=match(frequency)
            group=max(2,min(16,len(x)//16))
            count=len(x)//group
            cross=(base[:count*group]*np.conj(target[:count*group])).reshape(count,group).mean(axis=1)
            centres=times[:count*group].reshape(count,group).mean(axis=1)
            weights=abs(cross)
            if not np.any(weights):
                raise ValueError("no usable cross phase")
            slope=np.polyfit(centres,np.unwrap(np.angle(cross)),1,w=np.sqrt(weights))[0]
            candidate=frequency+float(slope/(2*np.pi))
            if abs(candidate-initial_frequency_hz)>max_refine_hz:
                raise ValueError("frequency fit left the permitted neighbourhood")
            frequency=candidate
        base,target,start,score=match(frequency)
        gain=np.vdot(target,base)/np.vdot(target,target)
        power=float(np.mean(abs(gain*target)**2))
        if power<=0:
            raise ValueError("no fitted reference power")
        nmse=float(10*np.log10(max(float(np.mean(abs(base-gain*target)**2))/power,1e-15)))
        return ReferenceAlignment(start,frequency,complex(gain),score,nmse)
