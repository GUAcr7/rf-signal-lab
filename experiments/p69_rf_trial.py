"""Derive P69 trial from the immutable, actually exercised P68 workflow."""
import sys
from pathlib import Path
from datetime import datetime,timezone
from p45_checkpoint import ROOT,read,write,sha,rel
from p53_build_live_ai import replace_once as sub

def generate():
    parent=ROOT/'experiments/p68_rf_dashboard_trial.py'
    manifest=read(ROOT/'results/p68-final-20261026T023906Z/manifest.json')
    if sha(parent)!=manifest['files'][rel(parent)]['sha256']:raise ValueError('tested P68 orchestration changed')
    text=parent.read_text(encoding='utf-8')
    text=sub(text,"ap.add_argument('--link-confirmation',required=True,type=Path);a=ap.parse_args()",
        "ap.add_argument('--link-confirmation',required=True,type=Path);ap.add_argument('--build',required=True,type=Path);ap.add_argument('--review',required=True,type=Path);a=ap.parse_args()")
    start=text.index("    active=read(ROOT/'results/p67-active.json')")
    end=text.index("    cache=read(ROOT/'results/p59-source-active.json')",start)
    text=text[:start]+'''    build_path=a.build;build=read(build_path);proof=read(a.review)
    if (build['status']!='passed_P69_build_12_lifecycle_cases_not_deployed'
        or proof['status']!='passed_P69_math15_integrated14_states_shots_policy19'
        or proof['build_sha256']!=sha(build_path)):raise ValueError('P69 reviewed build required')
    if sha(ROOT/build['binary'])!=build['binary_sha256']:raise ValueError('P69 binary changed')
    for p,h in build['inputs_sha256'].items():
        if sha(ROOT/p)!=h:raise ValueError('P69 input changed '+p)
'''+text[end:]
    text=text.replace('p68-rf-dashboard','p69-rf-metrics').replace('/tmp/p35-p68-','/tmp/p35-p69-')
    text=text.replace('P68','P69').replace("summary['display_revision']!='p67'","summary['display_revision']!='p69'")
    text=sub(text,"[('tone',15),('bpsk',16),('qpsk',16),('qam16',16)]",
        "[('tone',15),('bpsk',30),('qpsk',30),('qam16',30)]")
    text=sub(text,"names=['dashboard.json','ai.json','ai-history.jsonl','progress.json','summary.json','last-display-packed.bin','fb.raw']",
        "names=['dashboard.json','ai.json','ai-history.jsonl','summary.json','last-display-packed.bin','fb.raw','metrics.json','metrics-history.jsonl']")
    text=sub(text,"for ext in ('json','bin','raw'))","for ext in ('json','bin','raw','metrics.json'))")
    return text,parent

if __name__=='__main__':
    code,parent=generate()
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p69-trial-code-%Y%m%dT%H%M%SZ');out.mkdir()
    path=out/'executed-trial.py';path.write_text(code,encoding='utf-8')
    write(out/'report.json',dict(status='generated_from_frozen_P68',parent=rel(parent),parent_sha256=sha(parent),
        code=rel(path),code_sha256=sha(path),entry=rel(Path(__file__)),entry_sha256=sha(Path(__file__))))
    exec(compile(code,str(path),'exec'),dict(__name__='__main__',__file__=str(path)))
