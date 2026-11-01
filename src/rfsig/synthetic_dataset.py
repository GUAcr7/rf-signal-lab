"""Versioned synthetic-only records; split complete independent waveforms first."""
from dataclasses import dataclass
import hashlib
import numpy as np
from .bpsk import map_bpsk
from .modulation import map_qpsk,map_qam16
from .pulse_shaping import rrc_taps,shape_symbols,normalize_mean_power

CLASSES=('BPSK','QPSK','16QAM')
SNR_DB=(10,15,20)
ROOT_SEED=20261011
FRAME=1024

def array_hash(array):
    return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()

@dataclass(frozen=True)
class SyntheticRecord:
    clean: np.ndarray
    noisy: np.ndarray
    bits: np.ndarray
    metadata: dict

def make_record(modulation,snr_db,index,frames=8,*,root_seed=ROOT_SEED):
    if modulation not in CLASSES or snr_db not in SNR_DB:
        raise ValueError('Unknown modulation or SNR condition')
    if isinstance(index,bool) or not isinstance(index,int) or not 0<=index<20:
        raise ValueError('record index must be integer 0..19')
    if isinstance(frames,bool) or not isinstance(frames,int) or not 1<=frames<=32:
        raise ValueError('frames must be integer 1..32')
    if isinstance(root_seed,bool) or not isinstance(root_seed,int) or not 0<=root_seed<2**32:
        raise ValueError('root seed must be a uint32 integer')
    c=CLASSES.index(modulation); s=SNR_DB.index(snr_db)
    # Channel conditions share the same distribution and exact schedule across classes.
    condition_entropy=[root_seed,100,s,index]
    source_entropy=[root_seed,200,c,s,index]
    noise_entropy=[root_seed,300,c,s,index]
    condition=np.random.default_rng(np.random.SeedSequence(condition_entropy))
    source=np.random.default_rng(np.random.SeedSequence(source_entropy))
    noise_rng=np.random.default_rng(np.random.SeedSequence(noise_entropy))
    sps=4 if index%2==0 else 8
    fs=1_000_000
    amplitude=float(condition.uniform(.6,1.4));phase=float(condition.uniform(-np.pi,np.pi))
    cfo_hz=float(condition.uniform(-.03,.03)*fs/sps)
    offset=int(condition.integers(0,sps));count=frames*FRAME
    symbol_count=int(np.ceil((count+offset)/sps))+32
    bits_per_symbol={'BPSK':1,'QPSK':2,'16QAM':4}[modulation]
    bits=source.integers(0,2,symbol_count*bits_per_symbol,dtype=np.uint8)
    symbols={'BPSK':map_bpsk,'QPSK':map_qpsk,'16QAM':map_qam16}[modulation](bits)
    taps=rrc_taps(.35,10,sps)
    shaped=shape_symbols(symbols,taps,sps)
    crop_start=len(taps)-1+offset
    clean=shaped[crop_start:crop_start+count]
    assert len(clean)==count
    clean,_=normalize_mean_power(clean)
    clean*=amplitude*np.exp(1j*(phase+2*np.pi*cfo_hz*np.arange(count)/fs))
    power=float(np.mean(np.abs(clean)**2));noise_power=power/10**(snr_db/10)
    noise=np.sqrt(noise_power/2)*(noise_rng.standard_normal(count)+1j*noise_rng.standard_normal(count))
    clean=clean.astype('<c8');noisy=(clean.astype(np.complex128)+noise).astype('<c8')
    measured_noise=noisy.astype(np.complex128)-clean.astype(np.complex128)
    measured_snr=float(10*np.log10(np.mean(np.abs(clean.astype(np.complex128))**2)/np.mean(np.abs(measured_noise)**2)))
    split='train' if index<14 else ('validation' if index<17 else 'test')
    record_id=f'sim-v1-{modulation}-snr{snr_db}-r{index:02}'
    meta={'record_id':record_id,'source':'SYNTHETIC_NOT_REAL_RF','modulation':modulation,'split':split,
          'root_seed':root_seed,'condition_entropy':condition_entropy,'source_entropy':source_entropy,'noise_entropy':noise_entropy,
          'sample_rate_hz':fs,'samples_per_symbol':sps,'symbol_rate_hz':fs/sps,'rolloff':.35,'rrc_span_symbols':10,
          'frame_length':FRAME,'frames':frames,'frame_starts':list(range(0,count,FRAME)),
          'nominal_snr_db':snr_db,'measured_record_snr_db':measured_snr,'snr_definition':'mean clean complex power / mean added complex-noise power after complex64 storage',
          'amplitude':amplitude,'phase_rad':phase,'cfo_hz':cfo_hz,'integer_timing_offset':offset,'full_convolution_crop_start':crop_start,
          'clean_sha256':array_hash(clean),'noisy_sha256':array_hash(noisy),'bits_sha256':array_hash(bits),
          'frame_sha256':[array_hash(f) for f in noisy.reshape(frames,FRAME)],
          'units':'dimensionless; not ADC counts or RF watts','channel_scope':'RRC + phase + CFO + integer timing + AWGN; no multipath/AGC/hardware impairments'}
    return SyntheticRecord(clean,noisy,bits,meta)

def validate_records(records):
    seen_ids=set();seen_sources=set();seen_frames=set()
    for r in records:
        if r['source']!='SYNTHETIC_NOT_REAL_RF' or r['split'] not in ('train','validation','test'):
            raise ValueError('Incorrect data provenance or split')
        if r['record_id'] in seen_ids or r['clean_sha256'] in seen_sources:
            raise ValueError('Repeated parent waveform across records/splits')
        if len(r['frame_sha256'])!=r['frames'] or len(r['frame_starts'])!=r['frames']:
            raise ValueError('Frame metadata mismatch')
        if len(set(r['frame_sha256']))!=r['frames'] or seen_frames.intersection(r['frame_sha256']):
            raise ValueError('Duplicated frames across records/splits')
        if r['modulation'] not in CLASSES or r['nominal_snr_db'] not in SNR_DB:
            raise ValueError('Unknown label or SNR')
        seen_ids.add(r['record_id']);seen_sources.add(r['clean_sha256']);seen_frames.update(r['frame_sha256'])
    return {'records':len(seen_ids),'independent_parent_waveforms':len(seen_sources),'unique_frames':len(seen_frames),'cross_split_waveform_leakage':False}
