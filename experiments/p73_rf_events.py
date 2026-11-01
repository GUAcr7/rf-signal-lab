"""Same fixed P72 early/late RF protocol with native event triplet capture."""
import sys
from pathlib import Path
from datetime import datetime,timezone
from p45_checkpoint import ROOT,read,write,sha,rel
from p53_build_live_ai import replace_once as sub
from p72_capture_uncertain import generate as parent_generate,evidence_code


def generate():
    manifest=read(ROOT/'results/p72-final-20261026T043517Z/manifest.json')
    parent=ROOT/'experiments/p72_capture_uncertain.py'
    if sha(parent)!=manifest['files'][rel(parent)]['sha256']:raise ValueError('P72 protocol changed')
    text,_=parent_generate()
    start=text.index("    if (build['status']");end=text.index("    if sha(ROOT/build['binary'])",start)
    text=text[:start]+'''    if (build['status']!='built_P73_event_diagnostic_offline_tests_pending'
        or proof['status']!='passed_P73_bounded_same_update_capture_and_frozen_policy'
        or proof['build_sha256']!=sha(build_path)):raise ValueError('P73 reviewed instrumentation required')
'''+text[end:]
    text=text.replace('p72-qam-diagnostic','p73-native-events').replace('/tmp/p35-p72-','/tmp/p35-p73-')
    text=sub(text,"rx.command('test ! -e $s/control')","rx.command('test ! -e $s/control');rx.command('export P73_EVENT_CAPTURE=1')")
    text=sub(text,'fixed_shots_s=[8,20,35],extra_uncertain_shots_per_phase=3',
                   'fixed_shots_s=[8],extra_uncertain_shots_per_phase=0,native_events=dict(maximum=12,per_state_age=3,onset_guard_s=2,minimum_same_state_gap_s=2,age_boundary_s=120)')
    start=text.index('                    captured=False;fixed=');end=text.index('                    finish_tx();',start)
    text=text[:start]+'''                    captured=False
                    while time.monotonic()-case['host_start']<seconds:
                        row=sample();elapsed=time.monotonic()-case['host_start']
                        if elapsed>=(6 if name=='tone' else 8) and not captured:
                            shot(phase+'-fixed',row);captured=True
                        time.sleep(.5)
'''+text[end:]
    text=text.replace("summary['display_revision']!='p69'","summary['display_revision']!='p73'")
    text=sub(text,'                archive(c,rx,stage,names)',
        "                event_text=c.optional(rx,stage+'/data/event-history.jsonl')\n                events=[json.loads(line) for line in event_text.splitlines() if line.startswith('{')]\n                if not 1<=len(events)<=12 or [v['id'] for v in events]!=list(range(1,len(events)+1)):raise ValueError('native event manifest invalid')\n                c.record['events']=events;c.save();names.append('event-history.jsonl')\n                for e in events:names.extend('event-'+format(e['id'],'02d')+'.'+ext for ext in ('bin','json','metrics.json'))\n                archive(c,rx,stage,names)")
    text=text.replace('passed_P72_diagnostic_capture_archived_pending_independent_review',
                      'passed_P73_native_events_archived_pending_independent_review')
    text=text.replace('failed_or_unconfirmed_P72_diagnostic_capture','failed_or_unconfirmed_P73_native_events')
    return text,parent


if __name__=='__main__':
    text,parent=generate()
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p73-trial-code-%Y%m%dT%H%M%SZ');out.mkdir()
    path=out/'executed-trial.py';path.write_text(text,encoding='utf-8')
    write(out/'report.json',dict(status='generated_before_hardware',parent=rel(parent),parent_sha256=sha(parent),code=rel(path),code_sha256=sha(path),entry_sha256=sha(Path(__file__))))
    exec(compile(text,str(path),'exec'),dict(__name__='__main__',__file__=str(path)))
