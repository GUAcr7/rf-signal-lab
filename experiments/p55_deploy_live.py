"""Continue the unchanged accepted model into current-boot calibrated live LCD."""
import subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
from p45_checkpoint import ROOT,read,write,sha,rel

def main():
    recovered_path=ROOT/'results/p55-recovery-flow-20261024T075938Z/report.json';recovered=read(recovered_path)
    if recovered['status']!='passed_ARM_then_current_warm_RF_LCD_clock_IQ_pixels_and_units':raise ValueError('current warm recovery required')
    prior_path=ROOT/'results/p54-flow-20261024T043250Z/report.json';prior=read(prior_path)
    arm=ROOT/recovered['ARM']
    if sha(arm)!=recovered['ARM_sha256']:raise ValueError('actual ARM evidence changed')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p55-live-flow-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    r=dict(status='preflight',stages=[v for v in prior['stages'] if v['exit_code']==0],
        dataset=prior['dataset'],train=prior['train'],freeze=prior['freeze'],test_acquisition=prior['test_acquisition'],
        independent_test=prior['independent_test'],ARM_verification=rel(arm),recovery=rel(recovered_path),recovery_sha256=sha(recovered_path),
        parent_interrupted_flow=rel(prior_path),parent_interrupted_flow_sha256=sha(prior_path),
        expected_boot=recovered['expected_boot'],classifier_modified_after_test=False,model_selection_used_baseline_test=False,
        deployment_driver_only_fix=True,heldout_RF_origin_boot=read(ROOT/prior['test_acquisition'])['expected_boot'])
    r['stages'].append(dict(label='ARM_deployment_protocol_fixed',report=rel(arm),report_sha256=sha(arm),exit_code=0))
    def save():write(out/'report.json',r)
    def run(label,script,wanted,*params,timeout=300):
        print(label,flush=True);r['status']=label;save()
        with (out/(label+'.stdout')).open('wb') as a,(out/(label+'.stderr')).open('wb') as b:
            q=subprocess.run([sys.executable,str(ROOT/'experiments'/script),*map(str,params)],cwd=ROOT,stdout=a,stderr=b,timeout=timeout)
        paths=[Path(s.strip())/'report.json' for s in (out/(label+'.stdout')).read_text('utf-8').splitlines() if Path(s.strip()).is_absolute() and (Path(s.strip())/'report.json').is_file()]
        row=dict(label=label,exit_code=q.returncode);r['stages'].append(row);save()
        if len(paths)==1:row.update(report=rel(paths[0]),report_sha256=sha(paths[0]));r[label]=rel(paths[0]);save()
        if q.returncode or len(paths)!=1:raise ValueError(label+' failed; evidence retained')
        if read(paths[0])['status']!=wanted:raise ValueError(label+' status differs')
        return paths[0]
    save();(out/'executed.py').write_bytes(Path(__file__).read_bytes());built=False
    try:
        pref=run('current_preflight','p46_preflight.py','read_only_both_boards_identified_DMA_idle')
        if read(pref)['boards']['COM8']['boot_id']!=r['expected_boot']:raise ValueError('boot changed again')
        smoke=run('current_smoke','p36_full_rx_run.py','passed_finite_full_returned_buffers_board_only_pending_host_retrieval',
            '--expected-boot',r['expected_boot'],'--build-report','results/p36-full-rx-build-20261021T031400Z/report.json','--blocks','2')
        source=run('current_source','p52_restore_tx.py','guard_and_peak256_sources_restored_inspected_checked_no_TX',
            '--source-report','results/p54-plan-20261024T042837Z/2026102315/report.json','--preflight',pref)
        tone=run('tone_capture','p46_known_source.py','passed_bounded_known_source_captures_pending_host_archive',
            '--source-report',source,'--rx-smoke',smoke,'--case','tone','--blocks','2')
        archives=run('tone_archives','p46_archive_cases.py','passed_all_known_source_raw_buffers_archived','--trial',tone,timeout=400)
        calibration=run('current_calibration','p55_calibrate_current.py','passed_tone_only_common_IF_calibration','--archives',archives)
        build=run('live_candidate_build','p53_build_live_ai.py','passed_offline_live_AI_lifecycle_frontend_parity_ARM_build_not_deployed',
            '--ARM-review',arm,'--source-report',source,'--calibration',calibration)
        built=True
        run('live','p53_live_ai_trial.py','passed_three_class_real_RF_live_ARM_AI_LCD_and_independent_archives','--build',build,timeout=700)
        r['live_verified']=True
    except Exception as e:r.update(error=repr(e),live_verified=False)
    r['status']='passed_real_RF_AI_independent_test_ARM_and_offline_live_candidate' if built else 'stopped_at_failed_or_unconfirmed_gate'
    save();print(out);print(r['status']);return 0 if built else 1
if __name__=='__main__':raise SystemExit(main())
