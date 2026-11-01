"""Sequential fresh-boot RX/LCD recovery suite. Stop on the first failed gate.

Starts from an accepted P37 merged trial; it never loads PL, reboots, transmits,
or edits startup. All hardware access belongs to one awaited child at a time.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from p32_session import ROOT


def read(path):return json.loads(path.read_text('utf-8'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--merged-trial',type=Path,required=True)
    p.add_argument('--build-report',type=Path,required=True)
    args=p.parse_args()
    parent=read(args.merged_trial)
    if (parent['status']!='passed_fresh_boot_merged_probe_and_software_clocks_only'
        or parent['guard_restored'] is not True or parent['fresh_empty_boot_verified'] is not True
        or parent['serial_closed'] is not True or parent['PL_programming_attempts']!=1
        or parent['overlay_apply_attempts']!=1 or parent['reboots_issued']!=1):
        raise ValueError('accepted fresh merged trial required')
    boot=parent['held_boot']
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p40-recovery-suite-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    r=dict(status='preflight',expected_boot=boot,stages=[],
        merged_trial=str(args.merged_trial.resolve()),merged_trial_sha256=sha(args.merged_trial),
        build_report=str(args.build_report.resolve()),build_report_sha256=sha(args.build_report),
        PL_or_overlay_changes=False,reboots_issued=0,TX_operations=False,startup_file_changes=False,
        automatic_retry=False,lossless_proven=False,PRODUCT_ID_FF_root_cause_closed=False)
    (out/'executed.py').write_bytes(Path(__file__).read_bytes())
    def save():(out/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    def run(label,script,expected,*params,timeout=240):
        command=[sys.executable,str(ROOT/'experiments'/script),*map(str,params)]
        stage=dict(label=label,script=script,command=command,started_utc=datetime.now(timezone.utc).isoformat())
        r['stages'].append(stage);r['status']='running_'+label;save()
        print('Starting '+label,flush=True)
        with (out/(label+'.stdout')).open('wb') as stdout,(out/(label+'.stderr')).open('wb') as stderr:
            try:
                child=subprocess.run(command,cwd=ROOT,stdout=stdout,stderr=stderr,timeout=timeout)
            except subprocess.TimeoutExpired:
                stage['completion_unconfirmed']=True;save();raise RuntimeError('child completion unknown: '+label)
        stage['exit_code']=child.returncode;stage['ended_utc']=datetime.now(timezone.utc).isoformat();save()
        if child.returncode:raise RuntimeError('child failed; no retry: '+label)
        lines=(out/(label+'.stdout')).read_text('utf-8').splitlines()
        reports=[]
        for line in lines:
            path=Path(line.strip())
            if path.is_absolute() and path.resolve().is_relative_to((ROOT/'results').resolve()) and path.is_dir() and (path/'report.json').is_file():
                reports.append(path/'report.json')
        if len(reports)!=1:raise ValueError('ambiguous child report: '+label)
        path=reports[0];value=read(path)
        if value['status']!=expected:raise ValueError('unaccepted child status: '+label)
        stage.update(report=str(path),report_sha256=sha(path));save()
        print('Passed '+label,flush=True)
        return path,value
    def archive(label,parent):
        return run(label,'p36_retrieve_file.py','compressed_and_raw_bytes_archived_identity_and_source_rechecked',
            '--expected-boot',boot,'--remote',parent['remote'],'--expected-bytes',parent['compressed_bytes'],
            '--expected-sha256',parent['compressed_sha256'],'--raw-bytes',parent['raw_bytes'],
            '--raw-sha256',parent['raw_sha256'])
    def monitor(label,clock,duration,cancel=0):
        params=['--expected-boot',boot,'--build-report',args.build_report,
            '--clock-acceptance',clock,'--duration-ms',duration,'--interval-ms',500]
        if cancel:params+=['--cancel-after-ms',cancel]
        return run(label,'p39_run_latest_panel.py','passed_latest_buffer_RX_LCD_and_independent_idle_readback',*params)
    save()
    try:
        clock_path,_=run('clock_readback','p36_clockwiz_readback.py','read_only_evidence_collected','--expected-boot',boot)
        clock,_=run('clock_acceptance','p37_accept_clock_readback.py',
            'passed_ARM32_clock_overflow_fix_driver_register_consistency_this_boot','--trial',args.merged_trial,'--readback',clock_path)
        run('RX_configuration','p35_prepare_finite_rx.py','bounded_RX_test_configuration_read_back','--expected-boot',boot)
        run('cancel_recreate_baseline','p33_rx_cancel_run.py','passed_finite_cancel_recreate_and_independent_idle_readback',
            '--expected-boot',boot,'--build-report',ROOT/'results/p33-rx-cancel-build-20261020T114319Z/report.json')
        smoke,_=run('sparse_baseline','p36_sparse_smoke.py','receiver_abi_layout_capture_and_release_verified','--expected-boot',boot)
        run('panel_baseline','p36_panel_snapshot_run.py','passed_frozen_sparse_analysis_and_framebuffer_draw_only',
            '--expected-boot',boot,'--smoke-report',smoke)
        short,short_value=monitor('short_monitor',clock,3000)
        short_archive,_=archive('short_prefix_archive',short_value)
        run('short_NumPy','p39_verify_results.py','passed_archived_displayed_prefix_NumPy_review',
            '--board-report',short,'--iq-archive',short_archive)
        cancelled,cancel_value=monitor('cancel_monitor',clock,15000,2000)
        cancel_archive,_=archive('cancel_prefix_archive',cancel_value)
        run('cancel_NumPy','p39_verify_results.py','passed_archived_displayed_prefix_NumPy_review',
            '--board-report',cancelled,'--iq-archive',cancel_archive)
        long,long_value=monitor('restarted_120s_monitor',clock,120000)
        long_archive,_=archive('long_prefix_archive',long_value)
        fb,fb_value=run('final_framebuffer','p36_fb_snapshot_run.py',
            'visible_framebuffer_bytes_saved_and_gzip_verified_board_side','--expected-boot',boot,
            '--panel-report',long,'--build-report',ROOT/'results/p36-fb-dump-build-20261021T031234Z/report.json')
        fb_archive,_=archive('framebuffer_archive',fb_value)
        final,_=run('final_NumPy_and_screen','p39_verify_results.py','passed_archived_displayed_prefix_NumPy_review',
            '--board-report',long,'--iq-archive',long_archive,'--fb-snapshot',fb,'--fb-archive',fb_archive)
        r.update(status='passed_fresh_boot_cancel_restart_120s_RX_LCD_and_archived_NumPy_review',
            clock_acceptance=str(clock),short_monitor=str(short),cancel_monitor=str(cancelled),
            longest_monitor=str(long),final_review=str(final),
            final_idle_verified=long_value['independent_final_idle_verified'],serial_closed=long_value['serial_closed'],
            final_native_summary=long_value['native_summary'],
            physical_LCD_animation_confirmed_in_P39_only=True)
    except Exception as exc:r.update(status='failed_stop_on_first_gate',error=repr(exc))
    r['ended_utc']=datetime.now(timezone.utc).isoformat();save()
    print(out);print(r['status'])
    return 0 if r['status'].startswith('passed_') else 1


if __name__=='__main__':raise SystemExit(main())
