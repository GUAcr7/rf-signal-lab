"""Read-only observation of a captured P48 cold boot; leave RX running for human observation."""
import argparse,json,re,time
from datetime import datetime,timezone
from pathlib import Path
from p32_session import ROOT
from p35_once_merged_trial import TrialConsole
from p43_accept_power_on import observed_origin
from p42_run_live_panel import validate_progress
from p45_checkpoint import read,write,sha,rel


def check_policy(value):
    if (value['consoleblank']!='0' or value['marker']!='RF_PANEL_NO_X_DPMS'
        or not re.search(r'pwm-2.*requested enabled.*duty: 50000 ns',value['PWM'])
        or re.search(r'(?m)^\s*\d+\s+\d+\s+(?:/\S*/)?(?:Xorg|xinit)(?:\s|$)',value['processes'])):
        raise ValueError('display sleep/backlight policy differs')
    return value


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('enable','status-before','capture','human-event'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--minimum-seconds',type=int,default=660,choices=range(660,901))
    args=p.parse_args();enable=read(args.enable);before=read(args.status_before);capture=read(args.capture);human=read(args.human_event)
    console=(args.capture.parent/'console.txt').read_text('utf-8');boot=before['boot_id']
    if (enable.get('display_revision')!='p48' or before['status']!='read_only_persistent_profile_state_collected'
        or before['enable_report_sha256']!=sha(args.enable) or not before['serial_closed']
        or not before['persistent_wrapper_selected'] or before['taint']!='0' or before['pending_present'] or before['disabled_present']
        or not before['native_process_observed'] or before['RX_buffer']!='1' or before['RX_scans']!=['1','1','0','0']):
        raise ValueError('captured autonomous P48 receiver required')
    if observed_origin(enable,before,capture,human,console)!='user_confirmed_power_cycle':raise ValueError('cold origin required')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p50-watch-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    r=dict(status='observing_cold_P48',stages=[],expected_boot=boot,minimum_running_seconds=args.minimum_seconds,
        inputs={k:dict(path=rel(v),sha256=sha(v)) for k,v in vars(args).items() if isinstance(v,Path)},
        progress_samples=[before['native_progress']],board_file_writes=False,RF_changes=False,PL_changes=False,
        reboots_issued=0,stop_issued=False,physical_screen_confirmation=False,serial_closed=False)
    (out/'executed.py').write_bytes(Path(__file__).read_bytes())
    def save():write(out/'report.json',r)
    board=None;save()
    def digest(path):
        board.command('f='+path);values=re.findall(r'^([0-9a-f]{64})\s+\S+\r?$',board.command('sha256sum $f'),re.M)
        if len(values)!=1:raise ValueError('ambiguous SHA')
        return values[0]
    def identity():
        if (board.value('/proc/sys/kernel/random/boot_id')!=boot or board.value('/proc/sys/kernel/tainted')!='0'
            or digest('/etc/rcS.d/S99board')!=enable['wrapper_sha256']):raise ValueError('boot/kernel/guard changed')
    def policy():
        return check_policy(dict(consoleblank=board.value('/sys/module/kernel/parameters/consoleblank'),
            marker=board.value('/run/p44-display-policy'),PWM=board.command('cat /sys/kernel/debug/pwm'),
            processes=board.command('ps -eww -o pid,ppid,args')))
    try:
        board=TrialConsole('COM8',r,save,out);board.shell();identity()
        if digest('/run/p42-000043/monitor')!=enable['installed_files_sha256']['monitor']:raise ValueError('P48 RAM binary differs')
        r['policy_before']=policy();save()
        state=read(ROOT/'TX-SOURCE-STATUS.json');current=state['p50_current']
        current.update(status='P50_captured_cold_P48_observation_in_progress',expected_boot=boot,board_shutdown_issued=False,
            halt_observed=False,RX_idle=False,watch_report=rel(out/'report.json'),serial_closed=False)
        state.update(status=current['status'],updated=datetime.now(timezone.utc).isoformat());write(ROOT/'TX-SOURCE-STATUS.json',state)
        write(ROOT/'results/p50-active.json',current)
        start=ROOT/'START-HERE.md';old=start.read_text('utf-8')
        start.write_text('# 从这里恢复项目工作\n\n**P50新版真断电启动观察进行中，接收仍运行。** 当前boot '+boot+'；先读'+rel(out/'report.json')+'及results/p50-active.json。COM8由观察工具独占。下方已关机/idle描述均为此前历史，不能重放。\n\n'+old.split('\n',1)[1],encoding='utf-8')
        deadline=time.monotonic()+args.minimum_seconds+90
        while True:
            board.command('g=/run/p42-000043/data/progress.json')
            rows=[json.loads(s) for s in board.command('cat $g').splitlines() if s.startswith('{')]
            if len(rows)!=1:raise ValueError('missing progress')
            value=validate_progress(rows[0],0,r['progress_samples'][-1])
            if value['state']!='running' or value['display_updates']<=r['progress_samples'][-1]['display_updates']:
                raise ValueError('no continuing updates')
            r['progress_samples'].append(value);save()
            print(f"RX elapsed {value['elapsed_software_s']:.1f}s updates {value['display_updates']}",flush=True)
            if value['elapsed_software_s']>=args.minimum_seconds and len(r['progress_samples'])>=4:break
            if time.monotonic()>deadline:raise ValueError('observation deadline')
            time.sleep(10)
        identity();r['policy_after']=policy()
        r.update(status='passed_cold_P48_progress_over_660s_RX_left_running',RX_left_running=True,
            elapsed_software_s=r['progress_samples'][-1]['elapsed_software_s'],display_updates=r['progress_samples'][-1]['display_updates'])
    except Exception as error:r.update(status='failed_or_unconfirmed_RX_state_must_be_rechecked',error=repr(error))
    finally:
        if board:board.close()
        r.update(serial_closed=True,ended_utc=datetime.now(timezone.utc).isoformat());save()
        state=read(ROOT/'TX-SOURCE-STATUS.json');state['p50_current'].update(status=r['status'],serial_closed=True,watch_report=rel(out/'report.json'))
        state.update(status=r['status'],updated=r['ended_utc']);write(ROOT/'TX-SOURCE-STATUS.json',state);write(ROOT/'results/p50-active.json',state['p50_current'])
    print(out);print(r['status']);return 0 if r['status'].startswith('passed_') else 1


if __name__=='__main__':raise SystemExit(main())
