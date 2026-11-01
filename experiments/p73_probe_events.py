"""Fixed offline ablations of actual failed and successful RF blocks.

Every perturbation is reported; no best phase/IF/timing is selected or deployed.
The phase and amplitude controls keep the modulation identity unchanged.
"""
import argparse,subprocess
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
from p45_checkpoint import ROOT,read,write,sha,rel
from p37_review_archives import decode_rx12
from rfsig.rf_ai_calibration import adapt_calibrated
from rfsig.trainable_cnn import preprocess,patches,forward
from rfsig.cnn_quantization import quantized_forward

PROTOCOL=dict(phase_degrees=list(range(0,360,45)),amplitude_scale=[.25,1,4],
              IF_perturbation_hz=[-1000,-500,0,500,1000],raw_shift_samples=list(range(0,128,16)),
              mode_comparison=['fp32','int8'],parameters_selected_for_deployment=False)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--review',required=True,type=Path);a=ap.parse_args();review=read(a.review)
    if review['status']!='completed_P73_same_update_events_full_history_and_frozen_replay':raise ValueError('reviewed actual IQ required')
    trial=ROOT/review['trial'];t=read(trial)
    if sha(trial)!=review['trial_sha256']:raise ValueError('trial changed')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p73-probes-%Y%m%dT%H%M%SZ');out.mkdir()
    r=dict(status='probing',protocol=PROTOCOL,review=rel(a.review),review_sha256=sha(a.review),
           board_operations=False,model_modified=False,classification_fix_deployed=False,rows=[])
    write(out/'protocol.json',PROTOCOL)
    frozen=read(ROOT/'results/p52-export-20261024T043113Z/report.json')
    for v in frozen['frozen_inputs'].values():
        if sha(ROOT/v['path'])!=v['sha256']:raise ValueError('frozen input changed')
    with np.load(ROOT/frozen['frozen_inputs']['quantized']['path'],allow_pickle=False) as z:q=dict(z)
    with np.load(ROOT/frozen['frozen_inputs']['model']['path'],allow_pickle=False) as z:model=dict(z)
    files=trial.parent/'files'
    def classify(frames,mode='int8'):
        frames=np.asarray(frames,dtype=np.complex64)
        logits=(quantized_forward if mode=='int8' else forward)(patches(preprocess(frames)),q if mode=='int8' else model)
        pred=np.argmax(logits,axis=1).tolist()
        return dict(predictions=pred,accepted_class=pred[0] if len(set(pred))==1 else -1,logits=logits.tolist())
    try:
        for event in t['events']:
            base=f'event-{event["id"]:02d}';ai=read(files/(base+'.json'));raw=files/(base+'.bin')
            if sha(raw)!=t['files_sha256'][raw.name]:raise ValueError('IQ SHA differs')
            pairs=decode_rx12(raw.read_bytes());x=pairs[:,0].astype(float)+1j*pairs[:,1]
            cal=dict(status='known_tone_common_IF_calibrated',frequency_hz=ai['common_IF_hz'],shared_across_modulation_classes=True,modulation_labels_used=False)
            frames,_=adapt_calibrated(x,sample_rate_hz=30720000,calibration=cal)
            baseline=classify(frames)
            if baseline['predictions']!=ai['raw_predictions']:raise ValueError('baseline does not reproduce')
            row=dict(name=base,state=ai['state'],elapsed_s=ai['elapsed_s'],source_block_sequence=ai['source_block_sequence'],
                     IF_hz=ai['common_IF_hz'],baseline=baseline,fp32=classify(frames,'fp32'),phase=[],amplitude=[],IF=[],timing=[])
            child=subprocess.run([str(ROOT/frozen['frozen_inputs']['host']['path']),str(raw),str(ai['common_IF_hz']),'fp32'],capture_output=True,timeout=15)
            (out/(base+'-fp32-C.stdout')).write_bytes(child.stdout)
            if child.returncode:raise ValueError('frozen FP32 C replay failed')
            c=np.array([np.fromstring(line,sep=',') for line in child.stdout.decode().splitlines()])
            if c.shape!=(3,5) or c[:,4].astype(int).tolist()!=row['fp32']['predictions']:raise ValueError('FP32 C predictions differ')
            np.testing.assert_allclose(c[:,1:4],row['fp32']['logits'],rtol=1e-4,atol=5e-4)
            row['FP32_C_Python_parity']=True
            for degrees in PROTOCOL['phase_degrees']:
                rotated=frames*np.exp(1j*np.deg2rad(degrees))
                np.testing.assert_allclose(abs(rotated),abs(frames),rtol=1e-12,atol=1e-12)
                row['phase'].append(dict(degrees=degrees,**classify(rotated)))
            for scale in PROTOCOL['amplitude_scale']:
                row['amplitude'].append(dict(scale=scale,**classify(frames*scale)))
            for delta in PROTOCOL['IF_perturbation_hz']:
                changed=dict(cal,frequency_hz=cal['frequency_hz']+delta)
                varied,_=adapt_calibrated(x,sample_rate_hz=30720000,calibration=changed)
                row['IF'].append(dict(delta_hz=delta,**classify(varied)))
            for shift in PROTOCOL['raw_shift_samples']:
                varied,_=adapt_calibrated(np.roll(x,shift),sample_rate_hz=30720000,calibration=cal)
                row['timing'].append(dict(shift_samples=shift,**classify(varied)))
            row['amplitude_normalization_invariance']=all(z['predictions']==baseline['predictions'] for z in row['amplitude'])
            r['rows'].append(row);write(out/'report.json',r)
        summary=[]
        for state in ('UNCERTAIN','CLASSIFIED'):
            rows=[x for x in r['rows'] if x['state']==state]
            summary.append(dict(original_state=state,blocks=len(rows),
                FP32_consensus=sum(x['fp32']['accepted_class']>=0 for x in rows),
                FP32_QAM16=sum(x['fp32']['accepted_class']==2 for x in rows),
                phase_changes_block_predictions=sum(any(v['predictions']!=x['baseline']['predictions'] for v in x['phase']) for x in rows),
                phase_QAM16_consensus=sum(v['accepted_class']==2 for x in rows for v in x['phase']),
                phase_total=len(rows)*len(PROTOCOL['phase_degrees']),
                amplitude_invariant=sum(x['amplitude_normalization_invariance'] for x in rows),
                IF_QAM16_consensus=sum(v['accepted_class']==2 for x in rows for v in x['IF']),
                IF_total=len(rows)*len(PROTOCOL['IF_perturbation_hz']),
                timing_QAM16_consensus=sum(v['accepted_class']==2 for x in rows for v in x['timing']),
                timing_total=len(rows)*len(PROTOCOL['raw_shift_samples'])))
        r.update(status='completed_P73_exposed_RF_ablations_no_fix_deployed',summary=summary,
                 causality_limit='rotation sensitivity is model behavior; IF perturbation is not measured carrier drift; these exposed probes are not independent accuracy')
    except Exception as e:r.update(status='failed_P73_probes',error=repr(e))
    write(out/'report.json',r);print(out);print(r['status'])


if __name__=='__main__':main()
