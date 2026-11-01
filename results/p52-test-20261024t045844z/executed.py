"""One frozen-model evaluation on newly captured, disjoint real RF test groups."""
import argparse,time,json,subprocess
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
from p45_checkpoint import ROOT,read,write,sha,rel
from p52_make_dataset import frames_from_batch
from p52_train_real import metrics
from p37_review_archives import archive_bytes
from rfsig.real_rf_learning import validate_frame_groups
from rfsig.trainable_cnn import preprocess,patches,forward
from rfsig.cnn_quantization import quantized_forward

def main():
    p=argparse.ArgumentParser();p.add_argument('--frozen',required=True,type=Path);p.add_argument('--test-batch',required=True,type=Path);args=p.parse_args()
    frozen=read(args.frozen);batch=read(args.test_batch)
    if frozen['status']!='frozen_real_RF_model_before_unseen_test_capture' or batch['roles']!=['test'] or batch['frozen_model_sha256']!=sha(args.frozen):raise ValueError('frozen, separately captured test required')
    if (batch['plan_sha256']!=frozen['frozen_inputs']['plan']['sha256']
        or datetime.fromisoformat(batch['created_utc'])<datetime.fromisoformat(frozen['frozen_utc'])):
        raise ValueError('test capture must follow model freeze and use the exact protocol')
    inputs={k:ROOT/v['path'] for k,v in frozen['frozen_inputs'].items()}
    if any(sha(inputs[k])!=v['sha256'] for k,v in frozen['frozen_inputs'].items()):raise ValueError('frozen inputs changed')
    frames,rows,calibrations=frames_from_batch(args.test_batch,allowed_roles=('test',))
    train_data=read(inputs['dataset']);validate_frame_groups(train_data['frame_records']+rows)
    if len(rows)!=54 or len({r['seed'] for r in rows})!=3:raise ValueError('all three test seeds and 54 frames required')
    with np.load(inputs['model'],allow_pickle=False) as z:model=dict(z)
    with np.load(inputs['quantized'],allow_pickle=False) as z:q=dict(z)
    pch=patches(preprocess(frames));logits=dict(fp32=forward(pch,model),int8=quantized_forward(pch,q))
    truth=np.array([r['label'] for r in rows]);predictions={k:np.argmax(v,1) for k,v in logits.items()}
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p52-test-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False);(out/'fixtures').mkdir();(out/'C').mkdir()
    (out/'executed.py').write_bytes(Path(__file__).read_bytes())
    r=dict(status='evaluating_frozen_independent_REAL_RF_test',frozen=rel(args.frozen),frozen_sha256=sha(args.frozen),test_batch=rel(args.test_batch),test_batch_sha256=sha(args.test_batch),
        test_real_frames=54,independent_source_seeds=3,source_groups_disjoint=True,frame_random_split=False,source_class_given_to_inference=False,
        selected_mode=frozen['selected_mode'],class_order=frozen['class_order'],evaluation={k:metrics(truth,v) for k,v in predictions.items()},
        by_seed={},C_numeric_checks=[],board_operations=False,ARM_actual_execution=False,live_AI_on_LCD=False,
        scope='single controlled IF/symbol-rate/gains; no measured SNR, arbitrary signal, unknown rejection or frame-independent CI claim')
    def save():write(out/'report.json',r)
    save();Cpreds={k:[] for k in logits};fixtures=[];times=[]
    try:
        for group in batch['groups']:
            calibration=next(v['calibration'] for v in calibrations if v['seed']==group['seed'])
            archives=read(ROOT/group['archives'])
            for name in ('bpsk','qpsk','qam16'):
                entry=next(v for v in archives['cases'] if v['name']==name);path=Path(entry['report']);path=path if path.is_absolute() else ROOT/path
                _,raw=archive_bytes(path)
                for block in range(2):
                    file=out/'fixtures'/f'{group["seed"]}-{name}-{block}.bin';file.write_bytes(raw[block*262144:(block+1)*262144])
                    indices=[i for i,v in enumerate(rows) if v['seed']==group['seed'] and v['source_name']==name and v['block']==block]
                    if len(indices)!=3:raise ValueError('test indices differ')
                    for mode in ('fp32','int8'):
                        started=time.perf_counter();child=subprocess.run([str(inputs['host']),str(file),str(calibration['frequency_hz']),mode],capture_output=True,timeout=10);times.append((time.perf_counter()-started)*1000)
                        (out/'C'/(file.stem+'-'+mode+'.stdout')).write_bytes(child.stdout)
                        if child.returncode:raise ValueError('frozen C rejected test block')
                        a=np.array([np.fromstring(line,sep=',') for line in child.stdout.decode().splitlines()])
                        if a.shape!=(3,5):raise ValueError('C output layout differs')
                        np.testing.assert_allclose(a[:,1:4],logits[mode][indices],rtol=1e-4,atol=5e-4)
                        if not np.array_equal(a[:,4].astype(int),predictions[mode][indices]):raise ValueError('C/Python classes differ')
                        r['C_numeric_checks'].append(dict(seed=group['seed'],source=name,block=block,mode=mode,frames=3,matched=True));save()
                    fixtures.append(dict(path=rel(file),sha256=sha(file),seed=group['seed'],source_name=name,block=block,common_IF_hz=calibration['frequency_hz'],
                        expected_fp32=logits['fp32'][indices].tolist(),expected_int8=logits['int8'][indices].tolist(),truth=rows[indices[0]]['label']))
            selected=[i for i,v in enumerate(rows) if v['seed']==group['seed']]
            r['by_seed'][str(group['seed'])]={k:metrics(truth[selected],v[selected]) for k,v in predictions.items()};save()
        chosen=r['evaluation'][frozen['selected_mode']];plan=read(inputs['plan']);gate=plan['pass_gate']
        accepted=chosen['fraction_correct']>=gate['heldout_overall_accuracy_min'] and min(chosen['per_class_fraction_correct'])>=gate['heldout_each_class_accuracy_min']
        r.update(status='passed_independent_controlled_REAL_RF_classification_and_host_C_parity' if accepted else 'failed_independent_REAL_RF_classification_gate',
            AI_accepted_under_controlled_conditions=accepted,pass_gate=gate,test_predictions_used_to_select_model=False,model_modified_after_test=False,
            fixtures=fixtures,C_full_pipeline_matches=True,host_full_process_ms=dict(mean=float(np.mean(times)),max=float(max(times)),scope='process startup+file IO+mix/FIR/DC/RMS/CNN for three frames; not ARM latency'))
        np.savez_compressed(out/'evaluation.npz',frames=frames,truth=truth,**{k+'_prediction':v for k,v in predictions.items()},**{k+'_logits':v for k,v in logits.items()})
        r['evaluation_sha256']=sha(out/'evaluation.npz')
    except Exception as e:r.update(status='failed_or_unconfirmed_test',error=repr(e))
    save();print(out);print(r['status'])
    return 0 if r['status'].startswith('passed_') else 1
if __name__=='__main__':raise SystemExit(main())
