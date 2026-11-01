"""Fixed controlled-RF adapter, independent of modulation labels and model scores.

30.72 MS/s, common nominal +960 kHz IF, decimate 16 -> 1.92 MS/s.
With the controlled source's 240 ksymbol/s this is 8 samples/symbol.
Each DMA buffer is processed separately; unknown gaps are never filtered across.
This module does not detect signal presence, infer symbol rate, or reject noise.
"""
import numpy as np

SAMPLE_RATE_HZ=30_720_000
NOMINAL_IF_HZ=960_000
DECIMATION=16
OUTPUT_RATE_HZ=SAMPLE_RATE_HZ/DECIMATION
FRAME_LENGTH=1024
TAP_COUNT=513
CUTOFF_HZ=480_000
KAISER_BETA=8.6


def anti_alias_taps():
    n=np.arange(TAP_COUNT)-(TAP_COUNT-1)/2
    h=2*CUTOFF_HZ/SAMPLE_RATE_HZ*np.sinc(2*CUTOFF_HZ/SAMPLE_RATE_HZ*n)*np.kaiser(TAP_COUNT,KAISER_BETA)
    return h/h.sum()


def adapt_dma_block(iq,*,sample_rate_hz,nominal_if_hz):
    """Return complete 1024-point frames, with no padding or cross-DMA state.

    Rate/IF are explicit common acquisition conditions, not inferred from a label.
    Per-frame DC/RMS normalization remains the frozen classifier's responsibility.
    """
    if (isinstance(sample_rate_hz,(bool,np.bool_)) or isinstance(nominal_if_hz,(bool,np.bool_))
        or sample_rate_hz!=SAMPLE_RATE_HZ or nominal_if_hz!=NOMINAL_IF_HZ):
        raise ValueError('fixed controlled-RF rate and common nominal IF required')
    x=np.asarray(iq,dtype=np.complex128)
    if x.ndim!=1 or not x.size or not np.isfinite(x).all():raise ValueError('finite one-dimensional DMA block required')
    if len(x)<TAP_COUNT:raise ValueError('DMA block shorter than FIR')
    h=anti_alias_taps()
    mixed=x*np.exp(-2j*np.pi*NOMINAL_IF_HZ*np.arange(len(x))/SAMPLE_RATE_HZ)
    # Valid convolution excludes both FIR edge transients; no zero-filled edges.
    low=np.convolve(mixed,h,mode='valid')[::DECIMATION]
    count=len(low)//FRAME_LENGTH
    if not count or not np.isfinite(low).all():raise ValueError('no complete finite AI frame after edge guards')
    frames=low[:count*FRAME_LENGTH].reshape(count,FRAME_LENGTH).copy()
    meta=dict(input_samples=len(x),FIR_taps=TAP_COUNT,input_center_first=(TAP_COUNT-1)//2,
        decimation=DECIMATION,output_sample_rate_hz=OUTPUT_RATE_HZ,complete_frames=count,
        trailing_output_samples_discarded=len(low)-count*FRAME_LENGTH,
        frame_first_input_center=[(TAP_COUNT-1)//2+k*FRAME_LENGTH*DECIMATION for k in range(count)],
        no_cross_DMA_filtering=True,no_padding=True,nominal_IF_not_measured_carrier=True)
    return frames,meta
