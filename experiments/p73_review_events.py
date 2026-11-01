"""Replay both fixed snapshots and actual native event IQ with frozen Python/C."""
from pathlib import Path
from datetime import datetime,timezone
from p45_checkpoint import ROOT,read,write,sha,rel
from p53_build_live_ai import replace_once as sub


def generate():
    parent=ROOT/'experiments/p72_review_uncertain.py'
    manifest=read(ROOT/'results/p72-final-20261026T043517Z/manifest.json')
    if sha(parent)!=manifest['files'][rel(parent)]['sha256']:raise ValueError('P72 reviewed evaluator changed')
    text=parent.read_text(encoding='utf-8')
    text=text.replace('passed_P72_diagnostic_capture_archived_pending_independent_review','passed_P73_native_events_archived_pending_independent_review')
    text=text.replace("strftime('p72-review-","strftime('p73-review-")
    text=sub(text,"        files=a.trial.parent/'files'","""        files=a.trial.parent/'files'
        events=[json.loads(line) for line in (files/'event-history.jsonl').read_text().splitlines()]
        check('event manifest exact and bounded',events==t['events'] and 1<=len(events)<=12)
        quotas=collections.Counter((e['age_window'],e['state']) for e in events)
        check('per-state age quotas',all(n<=3 for n in quotas.values()))
        for e in events:
            base='event-'+format(e['id'],'02d');ai=read(files/(base+'.json'))
            check('event same update '+base,e['same_update_capture'] and ai['source_block_sequence']==e['source_block_sequence'] and ai['state']==e['state'])
            t['shots'].append(dict(id=e['id'],base=base,label='native-'+str(e['age_window'])+'-'+e['state'],AI=ai,trigger=None))
""")
    text=sub(text,"base='shot-'+format(shot['id'],'02d');ai=read", "base=shot.get('base','shot-'+format(shot['id'],'02d'));ai=read")
    text=text.replace('completed_P72_diagnostic_full_history_and_frozen_replay','completed_P73_same_update_events_full_history_and_frozen_replay')
    text=text.replace('failed_or_unconfirmed_P72_review','failed_or_unconfirmed_P73_review')
    text=text.replace("next_step='compare actual uncertain and classified IQ; if none, capture on-board at exact uncertain update'",
                      "next_step='compare actual native uncertain and classified IQ; keep the model and consensus frozen'")
    return text,parent


if __name__=='__main__':
    text,parent=generate()
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p73-review-code-%Y%m%dT%H%M%SZ');out.mkdir()
    p=out/'executed-review.py';p.write_text(text,encoding='utf-8')
    write(out/'report.json',dict(parent=rel(parent),parent_sha256=sha(parent),code=rel(p),code_sha256=sha(p)))
    exec(compile(text,str(p),'exec'),dict(__name__='__main__',__file__=str(p)))
