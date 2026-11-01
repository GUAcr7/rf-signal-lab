"""Checked portable IQ loader. No receiver, serial, network or AI dependency."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import numpy as np

KEYS=('tone','bpsk','qpsk','qam16')


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def inside(root,name):
    if not isinstance(name,str) or '\\' in name or name.startswith('/'):
        raise ValueError('Expected portable relative path')
    target=(root/name).resolve()
    if not target.is_relative_to(root.resolve()):raise ValueError('Path outside learning kit')
    return target


@dataclass(frozen=True)
class Record:
    key:str
    label:str
    iq_counts:np.ndarray  # [DMA buffer, sample, I/Q], signed ADC codes
    iq:np.ndarray         # [DMA buffer, sample], complex64; exactly I + 1j*Q
    metadata:dict


def load_kit(directory):
    """Verify every distributed file and both decoded representations.

    DMA boundaries are retained. Four buffers per waveform are repetitions of
    one cyclic source session, so no train/validation/test split is manufactured.
    """
    root=Path(directory).resolve();manifest=json.loads((root/'manifest.json').read_text('utf-8'))
    if (manifest.get('schema')!='rfsig.rf_learning_kit.v1' or manifest.get('hardware_required') is not False
        or manifest.get('independent_ML_benchmark_eligible') is not False
        or manifest.get('split')!='unassigned_learning_only'
        or manifest.get('ADC_gaps')!='unknown' or manifest.get('lossless_proven') is not False):
        raise ValueError('Unexpected learning-only data contract')
    listed=set()
    for entry in manifest['files']:
        name=entry['path']
        if name in listed:raise ValueError('Duplicate file in manifest')
        listed.add(name);path=inside(root,name)
        if path.stat().st_size!=entry['bytes'] or digest(path)!=entry['sha256']:
            raise ValueError('File hash/size mismatch: '+name)
    rows=manifest['records']
    if len(rows)!=4 or {r['key'] for r in rows}!=set(KEYS):raise ValueError('Expected four original RF cases')
    records={}
    for row in rows:
        for key in ('npz','metadata','original_packed'):
            if row[key] not in listed:raise ValueError('Unlisted data dependency')
        metadata=json.loads(inside(root,row['metadata']).read_text('utf-8'))
        if (metadata['source']!='REAL_RF_SAVED' or metadata['known_label']!=row['label']
            or metadata['label_source']!='known_transmitter_configuration' or metadata['ai_prediction'] is not None
            or metadata['split']!='unassigned_learning_only' or metadata['sample_rate_hz']!=30720000
            or metadata['ADC_gaps']!='unknown' or metadata['lossless_proven'] is not False):
            raise ValueError('Data identity/label interpretation differs')
        with np.load(inside(root,row['npz']),allow_pickle=False) as values:
            if set(values.files)!={'iq_counts','iq','sample_rate_hz'}:raise ValueError('Unexpected NPZ fields')
            counts=values['iq_counts'].copy();iq=values['iq'].copy();fs=values['sample_rate_hz']
        if (counts.shape!=(4,65536,2) or counts.dtype!=np.dtype('<i2') or iq.shape!=(4,65536)
            or iq.dtype!=np.dtype('<c8') or fs.shape!=() or fs.item()!=30720000
            or counts.min() < -2048 or counts.max()>2047 or not np.isfinite(iq).all()
            or not np.array_equal(iq.real,counts[:,:,0]) or not np.array_equal(iq.imag,counts[:,:,1])):
            raise ValueError('Decoded data shape/units differ')
        raw=inside(root,row['original_packed']).read_bytes()
        if len(raw)!=1048576 or hashlib.sha256(raw).hexdigest()!=metadata['raw_packed_sha256']:
            raise ValueError('Original packed evidence changed')
        low=np.frombuffer(raw,dtype='<u2')&0xfff
        decoded=((low.astype(np.int32)^0x800)-0x800).astype('<i2').reshape(4,65536,2)
        if not np.array_equal(counts,decoded):raise ValueError('RX12 decoding differs from original evidence')
        counts.flags.writeable=False;iq.flags.writeable=False
        records[row['key']]=Record(row['key'],row['label'],counts,iq,metadata)
    return manifest,records
