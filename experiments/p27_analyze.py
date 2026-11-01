"""Analyze explicit sparse prefixes only; never relabel them as full I/Q capture."""
import argparse
from datetime import datetime,timezone
import hashlib,json
import numpy as np
from p22_acquire_comparison import ROOT
from p26_audit_data import source
from p27_validate_observer import analyse
from rfsig.iq_io import load_iq_dma_s16
from rfsig.sparse_continuity import StridedReferenceMatcher


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--acquisition',required=True,type=str)
    parser.add_argument('--transfer',required=True,type=str)
    args=parser.parse_args()
    acq=ROOT/args.acquisition;transfer=ROOT/args.transfer
    record=json.loads((acq/'report.json').read_text('utf-8'))
    moved=json.loads((transfer/'report.json').read_text('utf-8'))
    if record['status']!='capture_and_tx_cleanup_verified' or moved['status']!='all_payloads_verified':
        raise RuntimeError('acquisition/cleanup/transfer unverified')
    if (ROOT/moved['acquisition']).resolve()!=acq.resolve():raise RuntimeError('wrong transfer association')
    meta=record['native_metadata']
    if (meta['blocks'],meta['dma_frames'],meta['prefix_raw_frames'],meta['stride'],meta['kept_frames_per_block'],meta['channels'])!=(512,65536,8192,8,1024,2):
        raise RuntimeError('unexpected sparse layout')
    if meta['complete_stream_saved'] or not meta['buffer_released']:raise RuntimeError('native contract invalid')
    entry=moved['files'][0];path=transfer/entry['local_file']
    if hashlib.sha256(path.read_bytes()).hexdigest()!=entry['sha256']:raise RuntimeError('source hash mismatch')
    iq=load_iq_dma_s16(path,channels=2)
    if len(iq)!=meta['blocks']*meta['kept_frames_per_block']:raise RuntimeError('prefix count mismatch')
    stamps=meta['timestamps']
    for index,row in enumerate(stamps):
        if row['block']!=index or not 0<=row['refill_start_s']<=row['refill_end_s']<=row['prefix_saved_s']:
            raise RuntimeError('invalid timestamps')
        if index and row['refill_start_s']<stamps[index-1]['prefix_saved_s']:
            raise RuntimeError('host timestamps not monotonic')
    tx=source('bpsk')
    ref=tx.iq*np.exp(-2j*np.pi*960000*np.arange(len(tx.iq))/30720000)
    matcher=StridedReferenceMatcher(ref,8)
    result=analyse(iq.reshape(512,1024),matcher)
    refill=np.array([r['refill_end_s']-r['refill_start_s'] for r in stamps])*1000
    copy=np.array([r['prefix_saved_s']-r['refill_end_s'] for r in stamps])*1000
    result.update(source=path.relative_to(ROOT).as_posix(),source_sha256=entry['sha256'],native_metadata=meta,
                  acquisition_record=acq.relative_to(ROOT).as_posix(),
                  nominal_drained_samples=512*65536,nominal_drained_duration_s=512*65536/30720000,
                  actually_saved_samples=len(iq),saved_sample_fraction=len(iq)/(512*65536),
                  observed_drained_MB_per_s=(512*65536*4)/meta['acquisition_s']/1e6,
                  refill_ms={'median':float(np.median(refill)),'p99':float(np.percentile(refill,99)),'max':float(np.max(refill))},
                  prefix_extraction_ms={'median':float(np.median(copy)),'p99':float(np.percentile(copy,99)),'max':float(np.max(copy))},
                  lossless_proven=False,
                  limits=['Each observed prefix covers the first 8192 raw sample positions, strided by 8; the rest is not saved.',
                          'No anti-alias filter is applied; these diagnostics are not a PSD/replay/model dataset.',
                          'Positions are modulo a periodic source; whole-period losses and unobserved internal events remain unverified.',
                          'Measured drain throughput is not full-record logging, FFT, inference or display throughput.'])
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p27-analysis-%Y%m%dT%H%M%SZ')
    out.mkdir(exist_ok=False)
    (out/'report.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    check=result['assessment']
    print(check['status'],'usable',check['usable_windows'],'jumps',check['detected_jump_count'],
          'unverified',check['unverified_boundary_count'],'drain MB/s',round(result['observed_drained_MB_per_s'],2))
    print(out)


if __name__=='__main__':main()
