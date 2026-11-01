"""Bounded early/late 16QAM diagnostic using the unchanged P69 binary.

Derives the exercised P69/P68 transport rather than creating another board IO
implementation. All generated code is saved before hardware access.
"""
import sys
from pathlib import Path
from datetime import datetime, timezone
from p45_checkpoint import ROOT, read, write, sha, rel
from p53_build_live_ai import replace_once as sub
from p69_rf_trial import generate as parent_generate


def evidence_code():
    parent = ROOT / 'experiments/p68_evidence.py'
    manifest = read(ROOT / 'results/p68-final-20261026T023906Z/manifest.json')
    if sha(parent) != manifest['files'][rel(parent)]['sha256']:
        raise ValueError('tested evidence helper changed')
    return sub(parent.read_text(encoding='utf-8'), '1<=len(names)<=32',
               '1<=len(names)<=64')


def archive(c, b, stage, names):
    namespace = {}
    exec(compile(evidence_code(), '<P72 bounded evidence>', 'exec'), namespace)
    return namespace['archive'](c, b, stage, names)


def generate():
    text, parent = parent_generate()
    text = sub(text, 'from p68_evidence import archive',
               'from p72_capture_uncertain import archive')
    text = text.replace('p69-rf-metrics', 'p72-qam-diagnostic')
    text = text.replace('/tmp/p35-p69-', '/tmp/p35-p72-')
    # Leave P69 build/offline proof status strings intact.
    text = sub(text, "duration_ms=300000,segments=[]", "diagnostic_protocol=dict(early_late_same_calibration=True,late_age_s=160,fixed_shots_s=[8,20,35],extra_uncertain_shots_per_phase=3,trigger_saved_state_may_differ=True,model_or_policy_change=False),duration_ms=300000,segments=[]")
    text = sub(text,
        "row=one_json(c.optional(rx,stage+'/data/ai.json'));c.record['samples'].append(row);c.save();return row",
        "row=one_json(c.optional(rx,stage+'/data/ai.json'));c.record['samples'].append(row)\n                    if row.get('ready') and 'calibration_ready_elapsed' not in c.record:c.record['calibration_ready_elapsed']=row['elapsed_s']\n                    c.save();return row")
    text = sub(text, 'def shot(label):', 'def shot(label,trigger=None):')
    text = sub(text, "number=len(c.record['shots'])+1;rx.command('echo '+str(number)+' >$s/shot')",
        "number=len(c.record['shots'])+1\n                    if number>16:raise ValueError('native snapshot budget exceeded')\n                    rx.command('echo '+str(number)+' >$s/shot')")
    text = sub(text, "dict(id=number,label=label,AI=data)",
               "dict(id=number,label=label,trigger=trigger,AI=data)")
    text = sub(text,
        "for name,seconds in [('tone',15),('bpsk',30),('qpsk',30),('qam16',30)]:",
        "for phase,name,seconds in [('pilot','tone',15),('early','qam16',45),('late','qam16',45)]:\n                    if phase=='late':\n                        while True:\n                            row=sample()\n                            if row['elapsed_s']>=c.record['calibration_ready_elapsed']+160:break\n                            if row['state']=='STOPPED':raise ValueError('RX ended before late window')\n                            time.sleep(3)")
    text = sub(text, 'case=dict(name=name,seconds=seconds',
               'case=dict(phase=phase,name=name,seconds=seconds')
    start = text.index('                    captured=False')
    end = text.index('                    finish_tx();', start)
    text = text[:start]+'''                    captured=False;fixed=set();triggered=0;last_trigger=-99
                    while time.monotonic()-case['host_start']<seconds:
                        row=sample();elapsed=time.monotonic()-case['host_start']
                        if name=='tone':
                            if elapsed>=6 and not captured:shot('pilot',row);captured=True
                        else:
                            due=next((offset for offset in (8,20,35) if offset not in fixed and elapsed>=offset),None)
                            if due is not None:
                                shot(phase+'-fixed-'+str(due),row);fixed.add(due)
                            elif row['state']=='UNCERTAIN' and triggered<3 and elapsed-last_trigger>=2 and elapsed<seconds-3:
                                shot(phase+'-uncertain-'+str(triggered+1),row);triggered+=1;last_trigger=elapsed
                        time.sleep(.5)
                    case.update(fixed_shots=sorted(fixed),uncertain_trigger_requests=triggered)
'''+text[end:]
    text = sub(text, "for ext in ('json','bin','raw','metrics.json'))",
               "for ext in ('json','bin','metrics.json'))")
    text = sub(text, '                archive(c,rx,stage,names)',
        "                uncertain=[s for s in c.record['shots'] if s['AI']['state']=='UNCERTAIN']\n                accepted=[s for s in c.record['shots'] if s['AI']['state']=='CLASSIFIED']\n                chosen=(uncertain[:1]+accepted[:1])\n                if len(chosen)<2:chosen+= [s for s in c.record['shots'] if s not in chosen][:2-len(chosen)]\n                c.record['framebuffer_shot_ids']=[s['id'] for s in chosen]\n                names.extend('shot-'+format(s['id'],'02d')+'.raw' for s in chosen)\n                archive(c,rx,stage,names)")
    text = sub(text, 'passed_P69_RF_dashboard_300s_archived_pending_independent_review',
               'passed_P72_diagnostic_capture_archived_pending_independent_review')
    text = text.replace('failed_or_unconfirmed_P69_RF_dashboard',
                        'failed_or_unconfirmed_P72_diagnostic_capture')
    return text, parent


def main():
    text, parent = generate()
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p72-trial-code-%Y%m%dT%H%M%SZ')
    out.mkdir()
    path=out/'executed-trial.py';path.write_text(text,encoding='utf-8')
    helper=out/'executed-evidence.py';helper.write_text(evidence_code(),encoding='utf-8')
    write(out/'report.json',dict(status='generated_before_hardware_access',
        parent=rel(parent),parent_sha256=sha(parent),code=rel(path),code_sha256=sha(path),
        archive_code=rel(helper),archive_code_sha256=sha(helper),
        entry=rel(Path(__file__)),entry_sha256=sha(Path(__file__))))
    exec(compile(text,str(path),'exec'),dict(__name__='__main__',__file__=str(path)))


if __name__=='__main__':main()
