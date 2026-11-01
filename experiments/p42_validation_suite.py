"""Sequential short/cancel/restart-ten-minute P42 acceptance. No automatic retry."""
import argparse
from datetime import datetime,timezone
import hashlib,json
from pathlib import Path
import subprocess,sys
from p32_session import ROOT
from p36_fb_snapshot_run import accepted_panel_parent

def read(p):return json.loads(p.read_text('utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ('short-report','merged-trial','build-report','clock-acceptance'):p.add_argument('--'+arg,type=Path,required=True)
    args=p.parse_args();short=read(args.short_report);boot=short['expected_boot']
    if short.get('schema')!='rfsig.p42_board.v1' or not accepted_panel_parent(short,boot) or short['duration_ms']!=3000:raise ValueError('completed short P42 required')
    if read(args.merged_trial).get('held_boot')!=boot:raise ValueError('merged boot differs')
    if short['binary_sha256']!=read(args.build_report)['binary_sha256']:raise ValueError('short build differs')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p42-suite-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    r=dict(status='preflight',expected_boot=boot,stages=[],short_report=str(args.short_report.resolve()),
        short_report_sha256=sha(args.short_report),reboots_issued=0,PL_changes=False,TX_operations=False,
        startup_file_changes=False,automatic_retry=False)
    (out/'executed.py').write_bytes(Path(__file__).read_bytes())
    def save():(out/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    def run(label,script,status,*params,timeout=180):
        stage=dict(label=label,command=[sys.executable,str(ROOT/'experiments'/script),*map(str,params)])
        r['stages'].append(stage);r['status']='running_'+label;save();print('Starting '+label,flush=True)
        with (out/(label+'.stdout')).open('wb') as stdout,(out/(label+'.stderr')).open('wb') as stderr:
            child=subprocess.run(stage['command'],cwd=ROOT,stdout=stdout,stderr=stderr,timeout=timeout)
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
    def monitor(label,duration,cancel=0):
        return run(label,'p42_run_live_panel.py','passed_long_running_RX_LCD_progress_and_independent_idle',
            '--expected-boot',boot,'--build-report',args.build_report,'--clock-acceptance',args.clock_acceptance,
            '--duration-ms',duration,'--interval-ms',500,'--cancel-after-ms',cancel,timeout=duration/1000+180 if duration else cancel/1000+180)
    save()
    try:
        run('short_archive_review','p42_review_session.py','passed_P42_archives_and_independent_NumPy','--trial',args.short_report)
        cancel,_=monitor('until_signal_cancel',0,5000)
        run('cancel_archive_review','p42_review_session.py','passed_P42_archives_and_independent_NumPy','--trial',cancel)
        long,value=monitor('restart_ten_minute',600000)
        final,review=run('long_archive_screen_clock_review','p42_review_session.py','passed_P42_archives_and_independent_NumPy',
            '--trial',long,'--with-screen','--merged-trial',args.merged_trial,timeout=240)
        r.update(status='passed_short_until_signal_stop_restart_10min_and_archived_review',
            cancel_report=str(cancel),long_report=str(long),final_review=str(final),screen_png=review['screen_png'],
            final_native_summary=value['native_summary'],independent_final_idle_verified=True,serial_closed=True,
            physical_LCD_animation_confirmed=False,ADC_gaps='unknown',lossless_proven=False)
    except Exception as exc:r.update(status='failed_stop_on_first_gate',error=repr(exc))
    r['ended_utc']=datetime.now(timezone.utc).isoformat();save();print(out);print(r['status'])
    return 0 if r['status'].startswith('passed_') else 1

if __name__=='__main__':raise SystemExit(main())
