"""Accept delayed desktop exit and pause P43 selection for its guarded reboot tool."""
from datetime import datetime,timezone
import hashlib,json,re
from pathlib import Path
from p32_session import ROOT,BoardConsole
from p35_once_merged_trial import AuditPort

def sha(b):return hashlib.sha256(b).hexdigest()
def main():
    parent=ROOT/'results/p44-policy-20261022T040536Z/report.json'
    policy=json.loads(parent.read_text('utf-8'))
    enable=json.loads((ROOT/'results/p43-enabled-20261022T033907Z/report.json').read_text('utf-8'))
    if not policy['service_wrapper_installed'] or policy.get('error')!="ValueError('desktop X owner remains')":raise ValueError('unexpected deployment state')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p44-prepared-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    r=dict(status='preflight',stages=[],policy_report=str(parent),policy_report_sha256=sha(parent.read_bytes()),
        installed_directory=policy['installed_directory'],installed_files_sha256=policy['installed_files_sha256'],
        reboots_issued=0,PL_changes=False,RF_changes=False,startup_paused=False)
    (out/'executed.py').write_bytes(Path(__file__).read_bytes())
    def save():(out/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    board=None;save()
    def digest(path):
        board.command('f='+path);v=re.findall(r'^([0-9a-f]{64})\s+\S+\r?$',board.command('sha256sum $f'),re.M)
        if len(v)!=1:raise ValueError('ambiguous SHA')
        return v[0]
    try:
        board=BoardConsole('COM8',r,save);board.port=AuditPort(board.port,out);board.shell()
        r['expected_boot']=board.value('/proc/sys/kernel/random/boot_id')
        if r['expected_boot']!=enable['expected_boot'] or board.value('/proc/sys/kernel/tainted')!='0' or 'Zynq-Tronlong' not in board.command('uname -a'):raise ValueError('identity differs')
        for name,wanted in policy['installed_files_sha256'].items():
            if digest(policy['installed_directory']+'/'+name)!=wanted:raise ValueError('policy file differs')
        if digest('/etc/init.d/xserver-nodm')!=policy['installed_files_sha256']['boot']:raise ValueError('policy not selected')
        r['consoleblank']=board.value('/sys/module/kernel/parameters/consoleblank')
        r['policy_marker']=board.value('/run/p44-display-policy')
        r['PWM']=board.command('cat /sys/kernel/debug/pwm')
        r['processes']=board.command('ps -eww -o pid,ppid,args')
        if (r['consoleblank']!='0' or r['policy_marker']!='RF_PANEL_NO_X_DPMS'
            or not re.search(r'pwm-2.*requested enabled.*duty: 50000 ns',r['PWM'])
            or re.search(r'(?m)^\s*\d+\s+\d+\s+(?:/\S*/)?(?:Xorg|xinit)(?:\s|$)',r['processes'])):raise ValueError('display policy not settled')
        board.command('ir=/sys/bus/iio/devices');text=board.command('for n in $ir/iio:device*;do echo $n;cat $n/name;done')
        names={n:d for d,n in re.findall(r'(/sys/bus/iio/devices/iio:device\d+)\r?\n([^\r\n]+)',text)}
        board.command('cd '+names['cf-ad9361-lpc'])
        if board.value('buffer/enable')!='0' or any(board.value('scan_elements/in_voltage'+str(i)+'_en')!='0' for i in range(4)):raise ValueError('RX not idle')
        if re.search(r'/run/p42-\d+/monitor',r['processes']):raise ValueError('native owner exists')
        d=enable['installed_directory'];board.command('j='+d)
        for name,wanted in enable['installed_files_sha256'].items():
            if digest(d+'/'+name)!=wanted:raise ValueError('P43 profile differs')
        if digest('/etc/rcS.d/S99board')!=enable['wrapper_sha256']:raise ValueError('unexpected startup selection')
        board.command('test ! -e $j/pending');board.command('test ! -e $j/disabled')
        board.command('z=/etc/rcS.d/.p44-pause');board.command('test ! -e $z')
        board.command('cp $j/original $z');board.command('chmod 755 $z')
        if digest('/etc/rcS.d/.p44-pause')!=enable['original_guard_sha256']:raise ValueError('staged guard differs')
        r['status']='pause_startup_selection_intent';save();board.command('mv $z /etc/rcS.d/S99board');board.command('sync',timeout=20)
        if digest('/etc/rcS.d/S99board')!=enable['original_guard_sha256']:raise ValueError('pause not applied')
        r.update(status='passed_policy_settled_original_guard_selected_for_next_guarded_cycle',startup_paused=True)
    except Exception as e:r.update(status='failed_or_unconfirmed',error=repr(e))
    finally:
        if board:board.close()
        r['serial_closed']=True;save();print(out);print(r['status'])
    return 0 if r['status'].startswith('passed_') else 1
if __name__=='__main__':raise SystemExit(main())
