"""Independently verify the saved ZIP, manifest, live sources and P32 state."""
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import zipfile
from p32_session import ROOT


def wide(p):
    s=str(p.resolve())
    return Path('\\\\?\\'+s) if os.name=='nt' and not s.startswith('\\\\?\\') else p


def sha(p):return hashlib.sha256(wide(p).read_bytes()).hexdigest()


def main():
    pointer=json.loads((ROOT/'results/p32-checkpoint-active.json').read_text('utf-8'))
    source=Path(pointer['report']);checkpoint=json.loads(source.read_text('utf-8'))
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p32-checkpoint-verification-%Y%m%dT%H%M%SZ')
    out.mkdir(exist_ok=False)
    checks=[]
    def check(name,ok):checks.append(dict(name=name,passed=bool(ok)))
    zipped=Path(pointer['zip'])
    check('checkpoint completed',checkpoint['status']=='P32_selected_source_evidence_snapshot_and_handoff_verified')
    check('ZIP external hash',sha(zipped)==pointer['zip_sha256']==checkpoint['zip_sha256'])
    with zipfile.ZipFile(zipped) as archive:
        check('ZIP CRC',archive.testzip() is None)
        check('exact ZIP entry count',len(archive.namelist())==checkpoint['snapshot_files'])
        for row in checkpoint['files']:
            check('ZIP bytes '+row['file'],hashlib.sha256(archive.read(row['file'])).hexdigest()==row['sha256'])
            check('snapshot bytes '+row['file'],sha(source.parent/'snapshot'/row['file'])==row['sha256'])
            live=Path(row['original']) if 'original' in row else ROOT/row['file']
            check('live bytes '+row['file'],sha(live)==row['sha256'])
    state=json.loads((ROOT/'TX-SOURCE-STATUS.json').read_text('utf-8'))
    check('current session authoritative',state['authoritative_current_field']=='p32_current')
    current=state['p32_current']
    check('current session active/idle original RF',current['current_state']=='both_boards_powered_on_idle_original_RF_restored')
    check('historical shutdown not mistaken for current',state['session_stop']['date_local']=='2026-10-19' and current['date_local']=='2026-10-20')
    check('merged hardware and AI not declared complete',not current['merged_firmware_loaded'] and not current['real_AI_accepted'])
    result=dict(status='passed' if all(c['passed'] for c in checks) else 'failed',
        checkpoint=str(source),checks=checks,checks_count=len(checks),board_operations=False,
        scope='Artifact hashes/state scopes, not new hardware function tests')
    (out/'report.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    pointer['independent_verification']=str(out/'report.json')
    (ROOT/'results/p32-checkpoint-active.json').write_text(json.dumps(pointer,indent=2)+'\n',encoding='utf-8')
    # Preserve the two failed copy attempts; add failure annotations without
    # replacing their original partial reports or deleting any partial files.
    for name,error in [('p32-checkpoint-20261020T111504Z','Windows CopyFile2 path length failure'),
            ('p32-checkpoint-20261020T111537Z','Python file IO without explicit extended path also rejected long snapshot filename')]:
        folder=ROOT/'results'/name
        if folder.exists():
            (folder/'failure-note.json').write_text(json.dumps(dict(status='incomplete_not_accepted',
                error=error,replaced_by=str(source),original_partial_files_preserved=True),indent=2)+'\n',encoding='utf-8')
    print(out);print(result['status']);print('artifact/state checks',len(checks))
    return 0 if result['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
