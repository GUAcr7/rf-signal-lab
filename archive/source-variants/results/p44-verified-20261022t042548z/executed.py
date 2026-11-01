"""Read back the installed policy after a completed >600-second fresh boot trial."""
import argparse,hashlib,json,re
from datetime import datetime,timezone
from pathlib import Path
from p32_session import ROOT,BoardConsole
from p35_once_merged_trial import AuditPort
from p43_finish_enable import reviewed

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('cycle','review','policy'):p.add_argument('--'+key,type=Path,required=True)
    args=p.parse_args();cycle,review=reviewed(args.cycle,args.review)
    policy=json.loads(args.policy.read_text('utf-8'))
    if (policy['status']!='passed_policy_settled_original_guard_selected_for_next_guarded_cycle'
        or cycle['native_summary']['elapsed_software_s']<660 or cycle.get('observation_seconds_requested',0)<660):raise ValueError('reviewed trial beyond old sleep threshold required')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p44-verified-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    r=dict(status='preflight',stages=[],inputs={k:dict(path=str(v.resolve()),sha256=sha(v)) for k,v in vars(args).items()},
        expected_boot=cycle['expected_boot'],board_writes=False,RF_changes=False,PL_changes=False,
        physical_visibility_confirmed=False,new_cold_boot_after_fix_verified=False)
    (out/'executed.py').write_bytes(Path(__file__).read_bytes())
    def save():(out/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    board=None;save()
    def digest(path):
        board.command('f='+path);v=re.findall(r'^([0-9a-f]{64})\s+\S+\r?$',board.command('sha256sum $f'),re.M)
        if len(v)!=1:raise ValueError('ambiguous SHA')
        return v[0]
    try:
        board=BoardConsole('COM8',r,save);board.port=AuditPort(board.port,out);board.shell()
        if board.value('/proc/sys/kernel/random/boot_id')!=cycle['expected_boot'] or board.value('/proc/sys/kernel/tainted')!='0' or 'Zynq-Tronlong' not in board.command('uname -a'):raise ValueError('identity changed')
        for name,wanted in policy['installed_files_sha256'].items():
            if digest(policy['installed_directory']+'/'+name)!=wanted:raise ValueError('policy changed')
        if digest('/etc/init.d/xserver-nodm')!=policy['installed_files_sha256']['boot']:raise ValueError('service policy changed')
        r['consoleblank']=board.value('/sys/module/kernel/parameters/consoleblank');r['marker']=board.value('/run/p44-display-policy')
        r['PWM']=board.command('cat /sys/kernel/debug/pwm');r['processes']=board.command('ps -eww -o pid,ppid,args')
        r['uptime']=board.command('cat /proc/uptime')
        if (r['consoleblank']!='0' or r['marker']!='RF_PANEL_NO_X_DPMS'
            or not re.search(r'pwm-2.*requested enabled.*duty: 50000 ns',r['PWM'])
            or re.search(r'(?m)^\s*\d+\s+\d+\s+(?:/\S*/)?(?:Xorg|xinit)(?:\s|$)',r['processes'])):raise ValueError('post-threshold display state failed')
        if board.value('/run/p43-init-boot')!=cycle['expected_boot']:raise ValueError('wrong startup')
        r.update(status='passed_new_warm_boot_over_600s_no_X_console_blank_disabled_backlight_enabled',
            native_elapsed_s=cycle['native_summary']['elapsed_software_s'],display_updates=cycle['native_summary']['display_updates'])
    except Exception as e:r.update(status='failed_or_unconfirmed',error=repr(e))
    finally:
        if board:board.close()
        r['serial_closed']=True;save();print(out);print(r['status'])
    return 0 if r['status'].startswith('passed_') else 1
if __name__=='__main__':raise SystemExit(main())
