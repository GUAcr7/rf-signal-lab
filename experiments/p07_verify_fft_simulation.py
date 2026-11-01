"""Independently check saved XSim FFT samples, frame boundaries and host-free cycles."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re

import numpy as np


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('evidence',type=Path)
    parser.add_argument('vectors',type=Path)
    args=parser.parse_args()
    evidence,vectors=args.evidence,args.vectors
    config=json.loads((vectors/'verification.json').read_text(encoding='utf-8'))
    for name,expected in config['vectors_sha256'].items():
        assert hashlib.sha256((vectors/name).read_bytes()).hexdigest()==expected, 'Reference changed: '+name
    record=json.loads((evidence/'run-record.json').read_text(encoding='utf-8-sig'))
    assert record['exit_code']==0 and not record['board_accessed'] and not record['bitstream_written']
    log=(evidence/'console.txt').read_text(encoding='utf-8-sig',errors='replace')
    match=re.search(r'P07_FFT_SELF_CHECK_PASS samples=(\d+) frames=(\d+) input_stalls=(\d+) output_stalls=(\d+) cycles=(\d+)',log)
    assert match,'No successful self-check marker'
    assert not re.search(r'(?:Fatal:|FFT_VALUE_MISMATCH|FFT_TIMEOUT|FFT_WRONG_|FFT_LEAKED_)',log)
    values=[int(x) for x in match.groups()]
    with (evidence/'output.csv').open(newline='',encoding='ascii') as f:rows=list(csv.DictReader(f))
    with (evidence/'cycles.csv').open(newline='',encoding='ascii') as f:cycles=list(csv.DictReader(f))
    n=config['points_per_frame']; frames=config['frames']
    assert len(rows)==2*frames*n==values[0] and len(cycles)==2*frames==values[1]
    reports=[]
    with np.load(vectors/'reference.npz',allow_pickle=False) as source:
        for epoch in (1,2):
            for frame,case in enumerate(config['cases']):
                offset=((epoch-1)*frames+frame)*n
                selected=rows[offset:offset+n]
                assert all(int(r['epoch'])==epoch and int(r['frame'])==frame and int(r['bin'])==index
                           for index,r in enumerate(selected))
                actual=np.array([int(r['real_counts'])+1j*int(r['imag_counts']) for r in selected])
                np.testing.assert_array_equal(actual,source[case['name']+'_expected'])
                error=float(np.max(np.abs(actual-source[case['name']+'_numpy'])))
                assert error<=config['numeric_acceptance_limit_counts']
                c={key:int(value) for key,value in cycles[(epoch-1)*frames+frame].items()}
                assert c['epoch']==epoch and c['frame']==frame
                assert c['first_input_cycle']<=c['last_input_cycle']<c['first_output_cycle']<=c['last_output_cycle']
                assert c['first_output_cycle']==int(selected[0]['cycle']) and c['last_output_cycle']==int(selected[-1]['cycle'])
                reports.append({**c,'name':case['name'],'max_numpy_complex_error_counts':error,
                                'first_input_to_first_output_cycles':c['first_output_cycle']-c['first_input_cycle'],
                                'first_input_to_last_output_cycles':c['last_output_cycle']-c['first_input_cycle']+1})
    durations=np.array([r['first_input_to_last_output_cycles'] for r in reports])
    verification={'schema':'rfsig.fft.simulation.verification.v1','checked_frames':len(reports),'checked_complex_samples':len(rows),
                  'all_bit_exact_vs_frozen_cmodel':True,'max_numpy_complex_error_counts':max(r['max_numpy_complex_error_counts'] for r in reports),
                  'input_stall_cycles':values[2],'output_stall_cycles':values[3],
                  'clock_period_ns':10,'frame_processing_cycles_min':int(durations.min()),'frame_processing_cycles_max':int(durations.max()),
                  'isolated_frame_average_samples_per_second_at_100MHz':float(n*1e8/durations.mean()),
                  'performance_scope':'simulated isolated frames, includes driver gaps/stalls; not board or sustained ADC/DMA throughput',
                  'partial_frame_reset_and_replay_checked':True,'board_accessed':False,'integrated_in_adc_dma':False,
                  'vectors_sha256':config['vectors_sha256'],
                  'evidence_sha256':{name:hashlib.sha256((evidence/name).read_bytes()).hexdigest() for name in ('output.csv','cycles.csv','tb_fft1024.sv','simulate_fft.tcl')},
                  'frames':reports}
    if record.get('driver_mode')=='back_to_back':
        verification['driver_mode']='back_to_back_ready_valid_driver'
        verification['overlapped_frame_latency_equivalent_rate_not_stream_throughput']=verification.pop('isolated_frame_average_samples_per_second_at_100MHz')
        verification['performance_scope']='simulated standalone stream; per-frame latency overlaps, so do not infer stream throughput from mean per-frame latency'
        verification['stream_epoch_metrics']=[]
        for epoch in (1,2):
            selected=[r for r in reports if r['epoch']==epoch]
            span=selected[-1]['last_output_cycle']-selected[0]['first_input_cycle']+1
            periods=[b['last_output_cycle']-a['last_output_cycle'] for a,b in zip(selected,selected[1:])]
            verification['stream_epoch_metrics'].append({'epoch':epoch,'frames':len(selected),'cycles':span,
                'simulated_samples_per_second_at_100MHz':len(selected)*n*1e8/span,
                'steady_output_frame_period_cycles':periods})
    (evidence/'verification.json').write_text(json.dumps(verification,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in verification.items() if k!='frames'},indent=2))


if __name__=='__main__':main()
