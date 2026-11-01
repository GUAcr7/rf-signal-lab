"""Preserve first merged synthesis, then apply a declarative-only XDC correction."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    active=json.loads((ROOT/'results/p30-active-build.json').read_text('utf-8'))
    work=Path(active['work'])
    out=ROOT/'results'/('p30-xdc-correction-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    out.mkdir(exist_ok=False)
    source=ROOT/'fpga/constraints/display_lvds_half_clock.xdc'
    target=work/'constraints/half_clock.xdc'
    old=sha(target)
    if old==sha(source):raise RuntimeError('correction already present')
    shutil.copy2(target,out/'before.xdc')
    shutil.copy2(source,out/'after.xdc')
    for file in work.glob('merged-synth.*'):shutil.copy2(file,out/('before-'+file.name))
    top_log=work/'project/combined.runs/synth_1/runme.log'
    shutil.copy2(top_log,out/'before-top-runme.log')
    shutil.copy2(source,target)
    report=dict(status='correction_prepared_requires_resynthesis',created_utc=datetime.now(timezone.utc).isoformat(),
        source=str(source),target=str(target),before_sha256=old,after_sha256=sha(target),
        reason='Designutils 20-1307: if/unset in prior XDC unsupported; move guards into build Tcl',
        board_operations=False,clock_period_or_exceptions_changed=False)
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    (ROOT/'results/p30-xdc-correction.json').write_text(json.dumps(dict(evidence=str(out/'report.json'),**report),indent=2)+'\n',encoding='utf-8')
    print(out)


if __name__=='__main__':main()
