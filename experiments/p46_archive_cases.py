"""Archive every returned buffer from the completed RF test; one COM8 owner."""
import argparse,json,hashlib,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
from p32_session import ROOT

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--trial',type=Path,required=True);args=p.parse_args()
    trial=json.loads(args.trial.read_text('utf-8'))
    if trial['status']!='passed_bounded_known_source_captures_pending_host_archive' or not trial['serial_closed'] or not trial['all_TX_cleanup_verified']:raise ValueError('completed cleaned-up trial required')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p46-archives-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    r=dict(status='archiving',trial=str(args.trial.resolve()),trial_sha256=sha(args.trial),cases=[],board_RF_writes=False)
    (out/'executed.py').write_bytes(Path(__file__).read_bytes())
    def save():(out/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    save()
    try:
        for case in trial['cases']:
            name=case['name'];row=dict(name=name,status='archiving');r['cases'].append(row);save();print('Archiving full '+name+' IQ',flush=True)
            cmd=[sys.executable,str(ROOT/'experiments/p36_retrieve_file.py'),'--expected-boot',trial['expected_boot'],
                '--remote',case['remote'],'--expected-bytes',str(case['compressed_bytes']),'--expected-sha256',case['compressed_sha256'],
                '--raw-bytes',str(case['raw_bytes']),'--raw-sha256',case['raw_sha256']]
            with (out/(name+'.stdout')).open('wb') as stdout,(out/(name+'.stderr')).open('wb') as stderr:
                process=subprocess.run(cmd,cwd=ROOT,stdout=stdout,stderr=stderr,timeout=300)
            row['exit_code']=process.returncode;save()
            if process.returncode:raise ValueError('archive failed '+name)
            paths=[Path(line.strip())/'report.json' for line in (out/(name+'.stdout')).read_text('utf-8').splitlines() if Path(line.strip()).is_absolute() and (Path(line.strip())/'report.json').is_file()]
            if len(paths)!=1:raise ValueError('archive report ambiguous')
            parent=json.loads(paths[0].read_text('utf-8'))
            if parent['status']!='compressed_and_raw_bytes_archived_identity_and_source_rechecked' or parent['verified_raw_sha256']!=case['raw_sha256']:raise ValueError('archive result differs')
            row.update(status='archived',report=str(paths[0]),report_sha256=sha(paths[0]));save();print('Archived '+name,flush=True)
        r['status']='passed_all_known_source_raw_buffers_archived'
    except Exception as e:r.update(status='failed_or_unconfirmed',error=repr(e))
    save();print(out);print(r['status'])
    return 0 if r['status'].startswith('passed_') else 1
if __name__=='__main__':raise SystemExit(main())
