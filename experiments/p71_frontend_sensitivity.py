"""Offline sensitivity probe on exposed P69 RF blocks; no fixes or new accuracy."""
from datetime import datetime,timezone
import numpy as np
from p45_checkpoint import ROOT,read,write,sha,rel
from p37_review_archives import decode_rx12
from rfsig.rf_ai_calibration import adapt_calibrated
from rfsig.trainable_cnn import preprocess,patches
from rfsig.cnn_quantization import quantized_forward

def main():
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p71-sensitivity-%Y%m%dT%H%M%SZ');out.mkdir()
    frozen=read(ROOT/'results/p52-export-20261024T043113Z/report.json')
    r=dict(status='analysing',board_operations=False,model_modified=False,rows=[],
        scope='sensitivity on previously exposed successful RF snapshots; cannot establish root cause of separate P70 uncertain blocks',
        perturbations_fixed_before_evaluation=dict(calibration_error_hz=[-1000,-500,-300,-100,0,100,300,500,1000],raw_sample_shift=[0,16,32,48,64,80,96,112]))
    try:
        for item in frozen['frozen_inputs'].values():
            if sha(ROOT/item['path'])!=item['sha256']:raise ValueError('frozen input changed')
        with np.load(ROOT/frozen['frozen_inputs']['quantized']['path'],allow_pickle=False) as z:quant=dict(z)
        folder=ROOT/'results/p59-p69-rf-metrics-20261026T025254567456Z/files'
        for number,name,wanted in ((3,'bpsk',0),(4,'qpsk',1),(5,'qam16',2)):
            ai=read(folder/f'shot-{number:02d}.json');raw=folder/f'shot-{number:02d}.bin'
            pair=decode_rx12(raw.read_bytes());x=pair[:,0].astype(float)+1j*pair[:,1]
            r.setdefault('inputs',{})[name]=dict(IQ=rel(raw),IQ_sha256=sha(raw),AI_sha256=sha(folder/f'shot-{number:02d}.json'))
            def infer(kind,value,signal,frequency):
                calibration=dict(status='known_tone_common_IF_calibrated',frequency_hz=frequency,shared_across_modulation_classes=True,modulation_labels_used=False)
                frames,metadata=adapt_calibrated(signal,sample_rate_hz=30720000,calibration=calibration)
                logits=quantized_forward(patches(preprocess(np.asarray(frames,dtype=np.complex64))),quant)
                predictions=np.argmax(logits,axis=1).tolist();accepted=predictions[0] if len(set(predictions))==1 else -1
                r['rows'].append(dict(signal=name,probe=kind,value=value,calibration_IF_hz=frequency,
                    raw_predictions=predictions,accepted_class=accepted,expected_class_for_offline_scoring_only=wanted,
                    agrees_with_known_source=accepted==wanted,logits=logits.tolist()))
            for delta in r['perturbations_fixed_before_evaluation']['calibration_error_hz']:
                infer('calibration_error_hz',delta,x,ai['common_IF_hz']+delta)
            # A <=112-sample circular shift only changes the discarded leading
            # boundary; frontend kept frames are inside the retained interior.
            for shift in r['perturbations_fixed_before_evaluation']['raw_sample_shift']:
                infer('raw_sample_shift',shift,np.roll(x,shift),ai['common_IF_hz'])
        summary=[]
        for name in ('bpsk','qpsk','qam16'):
            for kind in ('calibration_error_hz','raw_sample_shift'):
                rows=[v for v in r['rows'] if v['signal']==name and v['probe']==kind]
                summary.append(dict(signal=name,probe=kind,total=len(rows),correct=sum(v['agrees_with_known_source'] for v in rows),
                    uncertain=sum(v['accepted_class']==-1 for v in rows),wrong_accepted=sum(v['accepted_class']>=0 and not v['agrees_with_known_source'] for v in rows)))
        r.update(status='completed_offline_sensitivity_not_a_root_cause_or_new_accuracy_claim',summary=summary,
            no_parameters_selected_or_deployed=True,uncertain_P70_raw_IQ_still_required=True)
    except Exception as e:r.update(status='failed_sensitivity_analysis',error=repr(e))
    write(out/'report.json',r);print(out);print(r['status'])
if __name__=='__main__':main()
