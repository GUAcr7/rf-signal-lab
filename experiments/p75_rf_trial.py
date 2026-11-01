"""Prospectively frozen new-seed candidate RF regression, bounded RAM only."""
from datetime import datetime,timezone
from pathlib import Path
from p45_checkpoint import ROOT,read,write,sha,rel
from p53_build_live_ai import replace_once as sub
from p73_rf_events import generate as parent_generate
from p72_capture_uncertain import evidence_code


def archive(c,b,stage,names):
    code=sub(evidence_code(),'1<=len(names)<=64','1<=len(names)<=72')
    namespace={};exec(compile(code,'<P75 bounded archive>','exec'),namespace)
    return namespace['archive'](c,b,stage,names)


def generate():
    text,parent=parent_generate()
    text=text.replace('from p72_capture_uncertain import archive','from p75_rf_trial import archive')
    text=sub(text,"ap.add_argument('--review',required=True,type=Path);a=ap.parse_args()",
        "ap.add_argument('--review',required=True,type=Path);ap.add_argument('--plan',required=True,type=Path);a=ap.parse_args()")
    text=sub(text,"    build_path=a.build;build=read(build_path);proof=read(a.review)",
        "    build_path=a.build;build=read(build_path);proof=read(a.review)\n    plan=read(a.plan)\n    if plan['status']!='frozen_before_P75_RF_acquisition' or plan['build_sha256']!=sha(build_path):raise ValueError('predeclared protocol differs')")
    text=text.replace('built_P73_event_diagnostic_offline_tests_pending','passed_P75_phase_candidate_build_lifecycle12_not_deployed')
    text=text.replace('passed_P73_bounded_same_update_capture_and_frozen_policy','passed_P75_integrated14_states_shots_policy19')
    text=sub(text,"    source=upload_report['source']", "    source=upload_report['source']\n    if source['source_report']!=plan['source'] or source['source_report_sha256']!=plan['source_sha256']:raise ValueError('new planned seed not restored')")
    text=text.replace('p73-native-events','p75-phase-candidate').replace('/tmp/p35-p73-','/tmp/p35-p75-')
    text=text.replace("scope='exposed seed2315 controlled deployment regression, not independent AI accuracy'", "scope=plan['scope'],frozen_protocol=plan,plan=rel(a.plan),plan_sha256=sha(a.plan)")
    text=text.replace('late_age_s=160','late_age_s=180')
    text=text.replace('model_or_policy_change=False',"weights_frozen=True,inference_change='fixed8_phase_logits_mean',policy_change=False")
    text=sub(text,"[('pilot','tone',15),('early','qam16',45),('late','qam16',45)]",
        "[(v['phase'],v['source'],v['seconds']) for v in plan['segments']]")
    text=text.replace("c.record['calibration_ready_elapsed']+160","c.record['calibration_ready_elapsed']+180")
    text=text.replace('300000','360000').replace('timeout -k 2 330','timeout -k 2 390').replace('began<325','began<385')
    text=text.replace("summary['display_revision']!='p73'","summary['display_revision']!='p75'")
    text=text.replace('passed_P73_native_events_archived_pending_independent_review','passed_P75_fresh_RF_candidate_archived_pending_independent_review')
    text=text.replace('failed_or_unconfirmed_P73_native_events','failed_or_unconfirmed_P75_RF_candidate')
    return text,parent


if __name__=='__main__':
    text,parent=generate()
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p75-trial-code-%Y%m%dT%H%M%SZ');out.mkdir()
    path=out/'executed-trial.py';path.write_text(text,encoding='utf-8')
    write(out/'report.json',dict(parent=rel(parent),parent_sha256=sha(parent),code=rel(path),code_sha256=sha(path),entry_sha256=sha(Path(__file__))))
    exec(compile(text,str(path),'exec'),dict(__name__='__main__',__file__=str(path)))
