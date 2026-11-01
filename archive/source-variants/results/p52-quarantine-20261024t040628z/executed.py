"""Archive the incomplete transport-failed attempt separately, never as AI data."""
import subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
from p45_checkpoint import ROOT,read,write,sha,rel
from p37_review_archives import archive_bytes

def main():
    failed_path=ROOT/'results/p52-known-20261024T040217Z/report.json';failed=read(failed_path)
    preflight_path=ROOT/'results/p46-preflight-20261024T040507Z/report.json';preflight=read(preflight_path)
    if 'ClearCommError' not in failed['error'] or preflight['status']!='read_only_both_boards_identified_DMA_idle':raise ValueError('reviewed transport failure/current idle required')
    if preflight['boards']['COM8']['boot_id']!=failed['expected_boot'] or preflight['boards']['COM9']['boot_id']!=failed['TX_expected_boot']:raise ValueError('boot changed')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p52-quarantine-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    r=dict(status='preserving_interrupted_RF_attempt',failed_trial=rel(failed_path),failed_trial_sha256=sha(failed_path),
        preflight=rel(preflight_path),preflight_sha256=sha(preflight_path),cases=[],excluded_from_AI=True,
        historical_TX_completion_confirmed=False,current_TX_RX_idle_verified=True,board_RF_writes=False)
    def save():write(out/'report.json',r)
    save();(out/'executed.py').write_bytes(Path(__file__).read_bytes())
    try:
        for case in failed['cases']:
            cmd=[sys.executable,str(ROOT/'experiments/p36_retrieve_file.py'),'--expected-boot',failed['expected_boot'],
                '--remote',case['remote'],'--expected-bytes',str(case['compressed_bytes']),'--expected-sha256',case['compressed_sha256'],
                '--raw-bytes',str(case['raw_bytes']),'--raw-sha256',case['raw_sha256']]
            print('Preserving interrupted '+case['name'],flush=True)
            q=subprocess.run(cmd,capture_output=True,timeout=300)
            (out/(case['name']+'.stdout')).write_bytes(q.stdout);(out/(case['name']+'.stderr')).write_bytes(q.stderr)
            paths=[Path(s.strip())/'report.json' for s in q.stdout.decode().splitlines() if Path(s.strip()).is_absolute() and (Path(s.strip())/'report.json').is_file()]
            if q.returncode or len(paths)!=1:raise ValueError('partial raw preservation failed')
            _,raw=archive_bytes(paths[0])
            if len(raw)!=case['raw_bytes']:raise ValueError('partial buffer bytes differ')
            r['cases'].append(dict(name=case['name'],report=rel(paths[0]),report_sha256=sha(paths[0]),raw_sha256=case['raw_sha256'],excluded_from_AI=True));save()
        r['status']='preserved_partial_transport_failure_not_used_for_AI'
    except Exception as e:r.update(status='failed_partial_preservation',error=repr(e))
    save();print(out);print(r['status']);return 0 if r['status'].startswith('preserved_') else 1
if __name__=='__main__':raise SystemExit(main())
