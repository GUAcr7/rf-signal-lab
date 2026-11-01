"""Finite display candidate experiment; always attempt verified startup rearm.

Only RX/display application changes. No TX, RF-attribute, driver, PL or reboot
operations. The cold-verified persistent P42 binary is retained unchanged.
"""
import argparse
from datetime import datetime,timezone
import hashlib,json
from pathlib import Path
import subprocess,sys
from p32_session import ROOT


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text('utf-8'))
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def rel(p):return p.resolve().relative_to(ROOT.resolve()).as_posix()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build',type=Path,required=True);p.add_argument('--enable',type=Path,required=True);p.add_argument('--clock',type=Path,required=True)
    args=p.parse_args();build=read(args.build);enable=read(args.enable)
    if build['status']!='passed_native_mock_tests_and_ARM_build_not_board_test' or build['display_revision']!='p48' or build['test_count']<32:raise ValueError('P48 native checks required')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p48-suite-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    r=dict(status='preflight',stages=[],expected_boot=enable['expected_boot'],inputs={k:dict(path=rel(v),sha256=sha(v)) for k,v in vars(args).items()},
        TX_operations=False,RF_attribute_writes=False,PL_changes=False,reboots_issued=0,
        persistent_native_replaced=False,default_startup_display_revision='p42',startup_selection_rearmed=False)
    (out/'executed.py').write_bytes(Path(__file__).read_bytes())
    def save():
        write(out/'report.json',r)
        write(ROOT/'results/p48-active.json',dict(status=r['status'],report=rel(out/'report.json'),expected_boot=r['expected_boot'],
            startup_selection_rearmed=r['startup_selection_rearmed'],persistent_native_replaced=False,do_not_open_second_COM8_owner=r['status'].startswith('running_')))
    def run(label,script,accepted,*params):
        item=dict(label=label,command=[sys.executable,str(ROOT/'experiments'/script),*map(str,params)]);r['stages'].append(item)
        r['status']='running_'+label;save();print('Starting '+label,flush=True)
        with (out/(label+'.stdout')).open('wb') as stdout,(out/(label+'.stderr')).open('wb') as stderr:
            child=subprocess.run(item['command'],cwd=ROOT,stdout=stdout,stderr=stderr,timeout=240)
        item['exit_code']=child.returncode;save()
        if child.returncode:raise ValueError(label+' failed')
        paths=[]
        for line in (out/(label+'.stdout')).read_text('utf-8').splitlines():
            path=Path(line.strip())
            if path.is_absolute() and (path/'report.json').is_file() and path.is_relative_to(ROOT/'results'):paths.append(path/'report.json')
        if len(paths)!=1:raise ValueError('ambiguous report for '+label)
        path=paths[0];value=read(path)
        if value['status']!=accepted:raise ValueError('unaccepted '+label)
        item.update(report=rel(path),report_sha256=sha(path));save();print('Passed '+label,flush=True)
        return path,value
    save();pause_maybe=False;passed=False
    start=ROOT/'START-HERE.md';history=ROOT/datetime.now(timezone.utc).strftime('START-HERE-BEFORE-P48-%Y%m%dT%H%M%SZ.md');history.write_bytes(start.read_bytes())
    start.write_text('# 从这里恢复项目工作\n\n**P48小屏频偏单位候选验证进行中。** 先读results/p48-active.json及其报告；COM8由suite按阶段独占。阶段完成必须核实startup_selection_rearmed；不按下方旧状态重复启动。候选仅改显示应用，不改PL/驱动/射频参数或发射。P47学习包仍可直接使用。\n\n---\n\n'+start.read_text('utf-8').split('\n',1)[1],encoding='utf-8')
    try:
        pause_maybe=True
        run('pause_selection','p48_pause_startup.py','passed_idle_startup_selection_paused_no_hardware_reload','--enable-report',args.enable)
        trial,_=run('finite_candidate','p48_run_units_panel.py','passed_long_running_RX_LCD_progress_and_independent_idle',
            '--expected-boot',enable['expected_boot'],'--build-report',args.build,'--clock-acceptance',args.clock,'--duration-ms','10000')
        r['trial']=rel(trial);save()
        review,value=run('raw_and_framebuffer_review','p42_review_session.py','passed_P42_archives_and_independent_NumPy','--trial',trial,'--with-screen')
        r.update(review=rel(review),screen_png=value['screen_png']);save()
        units,_=run('frequency_and_glyphs','p48_verify_units.py','passed_P48_frequency_units_and_exact_framebuffer_glyphs','--trial',trial,'--review',review)
        r['units']=rel(units);passed=True
    except Exception as error:r.update(status='failed_candidate_or_unconfirmed',error=repr(error));save()
    finally:
        candidate_status=r['status'];r['candidate_checks_passed']=passed
        if pause_maybe:
            try:
                rearm,value=run('rearm_cold_verified_profile','p43_finish_enable.py','passed_persistent_profile_rearmed_after_two_archived_warm_boots',
                    '--cycle-one',ROOT/'results/p43-boot-cycle-20261022T030856Z/report.json','--review-one',ROOT/'results/p42-review-20261022T031116Z/report.json',
                    '--cycle-two',ROOT/'results/p43-boot-cycle-20261022T031333Z/report.json','--review-two',ROOT/'results/p42-review-20261022T031538Z/report.json',
                    '--current-cycle',ROOT/'results/p43-cold-cycle-20261022T104726Z/report.json','--current-review',ROOT/'results/p42-review-20261022T105059Z/report.json',
                    '--current-clock',args.clock)
                status,state=run('final_idle_profile_readback','p43_status.py','read_only_persistent_profile_state_collected','--enable-report',rearm)
                if (state['boot_id']!=enable['expected_boot'] or state['taint']!='0' or state['RX_buffer']!='0' or state['RX_scans']!=['0']*4
                    or state['native_process_observed'] or not state['persistent_wrapper_selected'] or state['pending_present'] or state['disabled_present']):
                    raise ValueError('final idle profile differs')
                r.update(startup_selection_rearmed=True,rearm=rel(rearm),final_status=rel(status),RX_idle=True,serial_closed=True)
            except Exception as error:r['rearm_error']=repr(error)
        r['status']='passed_P48_finite_display_units_candidate_and_original_startup_rearmed' if passed and r['startup_selection_rearmed'] else 'failed_or_unconfirmed_P48_candidate_or_rearm'
        r['candidate_status_before_rearm']=candidate_status;save()
    print(out);print(r['status']);return 0 if r['status'].startswith('passed_') else 1


if __name__=='__main__':raise SystemExit(main())
