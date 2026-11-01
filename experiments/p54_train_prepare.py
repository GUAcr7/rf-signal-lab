"""Longer training on existing train/validation only; no ports or baseline test."""
import argparse,os,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
from p45_checkpoint import ROOT,read,write,sha,rel

def main():
    p=argparse.ArgumentParser();p.add_argument('--plan',required=True,type=Path);args=p.parse_args()
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p54-learning-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    r=dict(status='training_validation_only',plan=rel(args.plan),plan_sha256=sha(args.plan),stages=[],board_operations=False,
        baseline_test_inputs_or_results_read=False,new_holdout_RF_acquired=False)
    def save():write(out/'report.json',r)
    def run(label,script,*params):
        env=os.environ.copy();env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
        with (out/(label+'.stdout')).open('wb') as a,(out/(label+'.stderr')).open('wb') as b:
            q=subprocess.run([sys.executable,str(ROOT/'experiments'/script),*map(str,params)],cwd=ROOT,env=env,stdout=a,stderr=b,timeout=600)
        paths=[Path(s.strip())/'report.json' for s in (out/(label+'.stdout')).read_text('utf-8').splitlines() if Path(s.strip()).is_absolute() and (Path(s.strip())/'report.json').is_file()]
        if q.returncode or len(paths)!=1:raise ValueError(label+' failed')
        r['stages'].append(dict(label=label,report=rel(paths[0]),report_sha256=sha(paths[0]),exit_code=q.returncode));r[label]=rel(paths[0]);save();return paths[0],read(paths[0])
    save();(out/'executed.py').write_bytes(Path(__file__).read_bytes())
    try:
        path,trained=run('train','p52_train_real.py','--dataset',args.plan.parent/'dataset/report.json','--plan',args.plan)
        selected=trained['validation'][trained['selected_mode']]
        r['validation']=trained['validation'];r['selected_mode']=trained['selected_mode'];save()
        if selected['fraction_correct']<.9 or min(selected['per_class_fraction_correct'])<.8:
            r['status']='validation_below_gate_no_new_RF_test_capture'
        else:
            frozen,_=run('freeze','p52_export_real.py','--trained',path)
            r.update(status='frozen_refined_model_before_new_holdout_RF',frozen=rel(frozen))
    except Exception as e:r.update(status='failed_refinement_preparation_no_RF_operations',error=repr(e))
    save();print(out);print(r['status']);return 0 if r['status'].startswith('frozen_') else 1
if __name__=='__main__':raise SystemExit(main())
