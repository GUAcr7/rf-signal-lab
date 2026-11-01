"""Independently read the saved ZIP, all manifest hashes and current doc links."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def main():
    active=json.loads((ROOT/'results/p31-checkpoint-active.json').read_text('utf-8'))
    manifest=Path(active['report'])
    report=json.loads(manifest.read_text('utf-8'))
    checks=[]
    def check(name,passed):
        checks.append(dict(check=name,passed=bool(passed)))
    check('checkpoint accepted only within stated scope',report['status']=='scoped_evidence_checkpoint_verified' and
        report['board_operations'] is False and all(c['passed'] for c in report['checks']))
    archive=manifest.parent/report['archive']['file']
    check('ZIP whole-file SHA',hashlib.sha256(archive.read_bytes()).hexdigest()==report['archive']['sha256'])
    with zipfile.ZipFile(archive) as bundle:
        check('ZIP CRC',bundle.testzip() is None)
        check('unique manifest entries',len(bundle.namelist())==len(set(bundle.namelist()))==len(report['files']))
        for row in report['files']:
            raw=bundle.read(row['path'])
            check('ZIP bytes '+row['path'],len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256'])
    documents=['START-HERE.md','docs/handoff/RESUME-20261019.md',
        'docs/experiments/EXP-HW-023-device-tree-cdc-and-kernel-recovery.md']
    for name in documents:
        source=ROOT/name
        for target in re.findall(r'\[[^\]]+\]\(([^)]+)\)',source.read_text('utf-8')):
            if target.startswith(('https://','http://','#')):
                continue
            local=target.split('#')[0]
            check('document link '+name+' -> '+local,(source.parent/local).exists())
    state=json.loads((ROOT/'TX-SOURCE-STATUS.json').read_text('utf-8'))['p31_current']
    check('current state is the saved checkpoint',state['checkpoint'].replace('\\','/')==manifest.relative_to(ROOT).as_posix())
    check('current RX boot after real guard startup',state['rx_boot_id']=='ebce10b9-e464-4b4c-b586-d4fd8d116e06' and state['guarded_script_full_warm_boot_tested'])
    check('kernel and merged hardware not falsely accepted',not state['kernel_root_cause_fixed'] and
        not state['combined_bitstream_generated'] and not state['combined_bitstream_programmed'] and
        not state['RF_display_concurrent_hardware_accepted'] and not state['real_AI_verified'] and not state['lossless_stream_verified'])
    check('RX idle and serial handles released',state['RX_buffer_enable']==0 and state['RX_scan_enable']==[0]*4 and state['serial_handles_closed'])
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p31-checkpoint-verification-%Y%m%dT%H%M%SZ')
    out.mkdir(exist_ok=False)
    status='passed' if all(c['passed'] for c in checks) else 'failed'
    result=dict(status=status,manifest=str(manifest),checks=checks,board_operations=False,
        scope='Archive bytes, scoped state and local documentation links only; not software/hardware functional acceptance')
    (out/'report.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(out)
    print(status,len(checks),'checks')
    for row in checks:
        if not row['passed']:
            print(row['check'])
    return 0 if status=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
