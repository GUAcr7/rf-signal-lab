"""Continue the already running RF batch through frozen testing and ARM checks.

One child at a time; no alternate RF route, retries or model tuning on test.
"""
import argparse,os,subprocess,sys,time
from datetime import datetime,timezone
from pathlib import Path
from p45_checkpoint import ROOT,read,write,sha,rel

def main():
    p=argparse.ArgumentParser()
    for name in ('batch','plan','preflight','rx-smoke'):p.add_argument('--'+name,type=Path,required=True)
    args=p.parse_args();out=ROOT/'results'/datetime.now(timezone.utc).strftime('p52-flow-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    r=dict(status='waiting_for_existing_train_validation_batch',stages=[],training_batch=rel(args.batch),serial_operations='none_until_existing_batch_completes',
        failure_policy='stop and retain evidence; do not tune on exposed test; restore baseline startup separately')
    def save():write(out/'report.json',r)
    def run(label,script,wanted,*params,timeout=300):
        r['status']=label;save();print(label,flush=True)
        env=os.environ.copy();env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
        with (out/(label+'.stdout')).open('wb') as a,(out/(label+'.stderr')).open('wb') as b:
            child=subprocess.run([sys.executable,str(ROOT/'experiments'/script),*map(str,params)],cwd=ROOT,env=env,stdout=a,stderr=b,timeout=timeout)
        row=dict(label=label,exit_code=child.returncode);r['stages'].append(row);save()
        paths=[Path(line.strip())/'report.json' for line in (out/(label+'.stdout')).read_text('utf-8').splitlines() if Path(line.strip()).is_absolute() and (Path(line.strip())/'report.json').is_file()]
        if child.returncode or len(paths)!=1:raise ValueError(label+' failed; see stdout/stderr')
        report=paths[0];row.update(report=rel(report),report_sha256=sha(report));save()
        if read(report)['status']!=wanted:raise ValueError(label+' did not pass')
        r[label]=rel(report);save();return report
    save();(out/'executed.py').write_bytes(Path(__file__).read_bytes())
    try:
        until=time.monotonic()+4200
        while True:
            batch=read(args.batch)
            if batch['status']=='passed_all_planned_REAL_RF_groups_archived_and_quality_checked':break
            if batch['status'].startswith('failed'):raise ValueError('original batch failed; no dependent actions')
            if time.monotonic()>until:raise ValueError('existing batch wait exceeded 70 minutes')
            time.sleep(10)
        if not batch['serial_closed'] or batch['roles']!=['train','validation']:raise ValueError('complete exclusive training/validation batch required')
        dataset=run('dataset','p52_make_dataset.py','passed_grouped_REAL_RF_training_validation_dataset_test_not_acquired','--batch',args.batch)
        trained=run('train','p52_train_real.py','trained_REAL_RF_validation_selected_test_not_acquired','--dataset',dataset,'--plan',args.plan,timeout=600)
        frozen=run('freeze','p52_export_real.py','frozen_real_RF_model_before_unseen_test_capture','--trained',trained)
        test=run('test_acquisition','p52_collect_batch.py','passed_all_planned_REAL_RF_groups_archived_and_quality_checked',
            '--plan',args.plan,'--preflight',args.preflight,'--rx-smoke',args.rx_smoke,'--roles','test','--frozen-model',frozen,timeout=2000)
        evaluated=run('independent_test','p52_evaluate_real.py','passed_independent_controlled_REAL_RF_classification_and_host_C_parity','--frozen',frozen,'--test-batch',test)
        arm=run('ARM_verification','p52_arm_verify.py','passed_independent_real_RF_ARM_full_frontend_CNN_matches_Python','--evaluation',evaluated,timeout=300)
        candidate=run('live_candidate_build','p53_build_live_ai.py','passed_offline_live_AI_lifecycle_frontend_parity_ARM_build_not_deployed','--ARM-review',arm)
        r.update(status='passed_real_RF_AI_independent_test_ARM_and_offline_live_candidate',live_candidate=rel(candidate))
    except Exception as e:r.update(status='stopped_at_failed_or_unconfirmed_gate',error=repr(e))
    save();print(out);print(r['status']);return 0 if r['status'].startswith('passed_') else 1
if __name__=='__main__':raise SystemExit(main())
