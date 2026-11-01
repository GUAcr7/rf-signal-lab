"""Archive a completed P42 session; independently verify its last displayed IQ."""
import argparse
from datetime import datetime,timezone
import hashlib,json
from pathlib import Path
import subprocess,sys
from p32_session import ROOT
from p36_fb_snapshot_run import accepted_panel_parent

def read(path):return json.loads(path.read_text('utf-8'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--trial',type=Path,required=True)
    p.add_argument('--with-screen',action='store_true')
    p.add_argument('--merged-trial',type=Path)
    args=p.parse_args();trial=read(args.trial);boot=trial['expected_boot']
    if trial.get('schema')!='rfsig.p42_board.v1' or not accepted_panel_parent(trial,boot):raise ValueError('completed P42 parent required')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p42-review-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    r=dict(status='preflight',stages=[],trial=str(args.trial.resolve()),trial_sha256=sha(args.trial),expected_boot=boot,
        board_RF_writes=False,PL_changes=False,reboots_issued=0,TX_operations=False,all_stream_samples_retained=False)
    (out/'executed.py').write_bytes(Path(__file__).read_bytes())
    def save():(out/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    def run(label,script,status,*params):
        stage=dict(label=label,command=[sys.executable,str(ROOT/'experiments'/script),*map(str,params)])
        r['stages'].append(stage);r['status']='running_'+label;save();print('Starting '+label,flush=True)
        with (out/(label+'.stdout')).open('wb') as stdout,(out/(label+'.stderr')).open('wb') as stderr:
            child=subprocess.run(stage['command'],cwd=ROOT,stdout=stdout,stderr=stderr,timeout=120)
        stage['exit_code']=child.returncode;save()
        if child.returncode:raise ValueError('stage failed: '+label)
        reports=[]
        for line in (out/(label+'.stdout')).read_text('utf-8').splitlines():
            path=Path(line.strip())
            if path.is_absolute() and path.resolve().is_relative_to(ROOT/'results') and (path/'report.json').is_file():reports.append(path/'report.json')
        if len(reports)!=1:raise ValueError('ambiguous child report')
        path=reports[0];value=read(path)
        if value['status']!=status:raise ValueError('unaccepted child report '+label)
        stage.update(report=str(path),report_sha256=sha(path));save();print('Passed '+label,flush=True)
        return path,value
    def archive(label,value):
        return run(label,'p36_retrieve_file.py','compressed_and_raw_bytes_archived_identity_and_source_rechecked',
            '--expected-boot',boot,'--remote',value['remote'],'--expected-bytes',value['compressed_bytes'],
            '--expected-sha256',value['compressed_sha256'],'--raw-bytes',value['raw_bytes'],'--raw-sha256',value['raw_sha256'])
    save()
    try:
        if args.merged_trial:
            merged=read(args.merged_trial)
            if merged.get('held_boot')!=boot:raise ValueError('merged clock parent has different boot')
            clocks,_=run('post_clock_readback','p36_clockwiz_readback.py','read_only_evidence_collected','--expected-boot',boot)
            clock,_=run('post_clock_acceptance','p37_accept_clock_readback.py',
                'passed_ARM32_clock_overflow_fix_driver_register_consistency_this_boot','--trial',args.merged_trial,'--readback',clocks)
            r['post_clock_acceptance']=str(clock)
        iq,_=archive('IQ_archive',trial);extra=[]
        if args.with_screen:
            fb,fb_value=run('framebuffer_snapshot','p36_fb_snapshot_run.py',
                'visible_framebuffer_bytes_saved_and_gzip_verified_board_side','--expected-boot',boot,
                '--panel-report',args.trial,'--build-report',ROOT/'results/p36-fb-dump-build-20261021T031234Z/report.json')
            pixels,_=archive('framebuffer_archive',fb_value)
            extra=['--fb-snapshot',fb,'--fb-archive',pixels]
        final,value=run('NumPy_last_prefix','p39_verify_results.py','passed_archived_displayed_prefix_NumPy_review',
            '--board-report',args.trial,'--iq-archive',iq,*extra)
        r.update(status='passed_P42_archives_and_independent_NumPy',final_review=str(final),serial_closed=True)
        if args.with_screen:r['screen_png']=value['screen_png']
    except Exception as exc:r.update(status='failed_stop_on_first_gate',error=repr(exc))
    r['ended_utc']=datetime.now(timezone.utc).isoformat();save();print(out);print(r['status'])
    return 0 if r['status'].startswith('passed_') else 1

if __name__=='__main__':raise SystemExit(main())
