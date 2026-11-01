"""Exact known-source quality reference from metadata, never an AI input branch."""
import numpy as np
from .tx_waveforms import make_tx_waveform,pack_tx_iq_le16

def reproduce_reference(ref,raw):
    mode=ref['modulation']
    if mode not in ('tone','BPSK','QPSK','16QAM'):raise ValueError('unsupported source reference')
    seed=ref.get('seed')
    if type(seed) is not int or not 0<=seed<2**32:raise ValueError('explicit source seed required')
    if (ref.get('sample_rate_hz')!=30720000 or ref.get('sample_count')!=131072
        or ref.get('digital_peak_counts')!=256 or ref.get('offset_hz')!=960000):
        raise ValueError('controlled source conditions differ')
    options=dict(sample_rate_hz=ref['sample_rate_hz'],samples_per_symbol=128,symbol_count=1024,
        seed=seed,offset_hz=ref['offset_hz'],digital_peak_counts=ref['digital_peak_counts'],
        rolloff=.35 if mode=='tone' else ref['rrc_rolloff'],span_symbols=10 if mode=='tone' else ref['rrc_span_symbols'])
    if mode!='tone' and (ref['samples_per_symbol']!=128 or ref['symbol_count']!=1024):raise ValueError('symbol layout differs')
    wave=make_tx_waveform(mode,**options)
    if pack_tx_iq_le16(wave.iq)!=raw:raise ValueError('source metadata does not reproduce exact TX bytes')
    return wave
