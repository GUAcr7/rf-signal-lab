"""After the baseline releases the boards, test the refined frozen model once."""
import argparse,json,subprocess,sys,time
from datetime import datetime,timezone
from pathlib import Path
from p45_checkpoint import ROOT,read,write,sha,rel

def main():
    p=argparse.ArgumentParser();p.add_argument('--learning',required=True,type=Path);p.add_argument('--wait-for-flow',required=True,type=Path);args=p.parse_args()
    learning=read(args.learning)
    if learning['status']!='frozen_refined_model_before_new_holdout_RF':raise ValueError('validation-passed frozen refinement required')
    plan=ROOT/learning['plan'];frozen=ROOT/learning['frozen']
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p54-flow-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    r=dict(status='waiting_for_baseline_board_release',stages=learning['stages'].copy(),plan=rel(plan),plan_sha256=sha(plan),
        dataset=rel(plan.parent/'dataset/report.json'),train=learning['train'],freeze=learning['freeze'],
        refinement=rel(args.learning),refinement_sha256=sha(args.learning),baseline_flow=rel(args.wait_for_flow),
        model_selection_used_baseline_test=False,excluded_baseline_test_seeds=[2026102310,2026102311,2026102312])
    def save():write(out/'report.json',r)
    def run(label,script,wanted,*params,timeout=300):
        print(label,flush=True);r['status']=label;save()
        with (out/(label+'.stdout')).open('wb') as a,(out/(label+'.stderr')).open('wb') as b:
            q=subprocess.run([sys.executable,str(ROOT/'experiments'/script),*map(str,params)],cwd=ROOT,stdout=a,stderr=b,timeout=timeout)
        row=dict(label=label,exit_code=q.returncode);r['stages'].append(row);save()
        paths=[Path(s.strip())/'report.json' for s in (out/(label+'.stdout')).read_text('utf-8').splitlines() if Path(s.strip()).is_absolute() and (Path(s.strip())/'report.json').is_file()]
        if q.returncode or len(paths)!=1:raise ValueError(label+' failed; evidence retained')
        row.update(report=rel(paths[0]),report_sha256=sha(paths[0]));r[label]=rel(paths[0]);save()
        if read(paths[0])['status']!=wanted:raise ValueError(label+' status failed')
        return paths[0]
    save();(out/'executed.py').write_bytes(Path(__file__).read_bytes())
    try:
        deadline=time.monotonic()+3000
        while True:
            try:previous=read(args.wait_for_flow)
            except json.JSONDecodeError:time.sleep(.2);continue
            if previous['status'] in ('stopped_at_failed_or_unconfirmed_gate','passed_real_RF_AI_independent_test_ARM_and_offline_live_candidate'):break
            if time.monotonic()>deadline:raise ValueError('baseline still owns serial; no new hardware actions')
            time.sleep(10)
        # Baseline outcome is not used to select the already frozen refinement.
        state=read(ROOT/'results/p52-active.json')
        if not state['serial_closed']:raise ValueError('baseline serial owner has not released')
        pref=run('preflight','p46_preflight.py','read_only_both_boards_identified_DMA_idle')
        test=run('test_acquisition','p52_collect_batch.py','passed_all_planned_REAL_RF_groups_archived_and_quality_checked',
            '--plan',plan,'--preflight',pref,'--rx-smoke',ROOT/'results/p36-full-rx-board-20261024T032807Z/report.json','--roles','test','--frozen-model',frozen,timeout=2000)
        evaluated=run('independent_test','p52_evaluate_real.py','passed_independent_controlled_REAL_RF_classification_and_host_C_parity','--frozen',frozen,'--test-batch',test)
        arm=run('ARM_verification','p52_arm_verify.py','passed_independent_real_RF_ARM_full_frontend_CNN_matches_Python','--evaluation',evaluated)
        run('live_candidate_build','p53_build_live_ai.py','passed_offline_live_AI_lifecycle_frontend_parity_ARM_build_not_deployed','--ARM-review',arm)
        r['status']='passed_real_RF_AI_independent_test_ARM_and_offline_live_candidate'
    except Exception as e:r.update(status='stopped_at_failed_or_unconfirmed_gate',error=repr(e))
    save();print(out);print(r['status']);return 0 if r['status'].startswith('passed_') else 1
if __name__=='__main__':raise SystemExit(main())
