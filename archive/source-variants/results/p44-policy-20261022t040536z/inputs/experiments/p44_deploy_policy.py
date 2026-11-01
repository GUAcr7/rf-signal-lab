"""Test, back up and install the conditional X init policy; no driver/PL reload."""
from datetime import datetime,timezone
import hashlib,json,re,subprocess,sys
from pathlib import Path
import xml.etree.ElementTree as ET
from p32_session import ROOT,BoardConsole
from p35_once_merged_trial import AuditPort
from p35_uart_files import upload
from p44_display_policy import render

def sha(b):return hashlib.sha256(b).hexdigest()
def main():
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=ROOT/'results'/('p44-policy-'+stamp);out.mkdir(exist_ok=False)
    d='/etc/p44-'+stamp;temp='/tmp/p35-p44-'+stamp[9:15]
    original_path=ROOT/'results/p44-policy-inputs-20261022T040311Z/xserver-original';original=original_path.read_bytes()
    parent=json.loads((original_path.parent/'report.json').read_text('utf-8'))
    if parent['status']!='exact_X_init_archived_and_profiles_read' or sha(original)!=parent['original_sha256']:raise ValueError('original changed')
    files=render(d,original);files['xserver-original']=files.pop('original')
    sources=['board/boot/p44-display-awake.sh','board/boot/p44-xserver-policy.sh.in','experiments/p44_display_policy.py','tests/test_p44_display_policy.py','experiments/p44_deploy_policy.py']
    hashes={s:sha((ROOT/s).read_bytes()) for s in sources}
    for name,data in files.items():(out/name).write_bytes(data)
    for s in sources:
        f=out/'inputs'/s;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes((ROOT/s).read_bytes())
    r=dict(status='testing',stages=[],installed_directory=d,inputs_sha256=hashes,installed_files_sha256={k:sha(v) for k,v in files.items()},
        original_readback=str(original_path.parent/'report.json'),original_sha256=sha(original),RF_changes=False,PL_changes=False,driver_unbinds=False,
        service_wrapper_installed=False,physical_display_after_policy_confirmed=False)
    def save():(out/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    board=None;save()
    def digest(path):
        board.command('f='+path);v=re.findall(r'^([0-9a-f]{64})\s+\S+\r?$',board.command('sha256sum $f'),re.M)
        if len(v)!=1:raise ValueError('ambiguous hash')
        return v[0]
    try:
        xml=out/'tests.xml';test=subprocess.run([sys.executable,'-m','pytest','tests/test_p44_display_policy.py','-q','--junitxml='+str(xml)],cwd=ROOT,capture_output=True,timeout=120)
        (out/'tests.stdout').write_bytes(test.stdout);(out/'tests.stderr').write_bytes(test.stderr)
        cases=list(ET.parse(xml).getroot().iter('testcase'))
        if test.returncode or len(cases)!=9 or any(list(c.iter(t)) for c in cases for t in ('failure','error','skipped')):raise ValueError('policy shell tests failed')
        if any(sha((ROOT/s).read_bytes())!=digest for s,digest in hashes.items()):raise ValueError('tested inputs changed')
        r.update(test_count=9,tests_sha256=sha(xml.read_bytes()));save()
        board=BoardConsole('COM8',r,save);board.port=AuditPort(board.port,out);board.shell()
        if 'Zynq-Tronlong' not in board.command('uname -a') or board.value('/proc/sys/kernel/random/boot_id')!='f65eb741-88fc-44c1-9cb7-8fced08ac86a' or board.value('/proc/sys/kernel/tainted')!='0':raise ValueError('identity changed')
        if digest('/etc/init.d/xserver-nodm')!=sha(original):raise ValueError('original service changed')
        r['before_X']=board.command('DISPLAY=:0 xset q');r['before_PWM']=board.command('cat /sys/kernel/debug/pwm');save()
        board.command('mkdir '+temp)
        for name,data in files.items():upload(board,temp+'/'+name,data)
        board.command('t='+temp);board.command('d='+d);board.command('mkdir $d')
        for name,data in files.items():
            board.command('cp $t/'+name+' $d/'+name);board.command('chmod 755 $d/'+name)
            if digest(d+'/'+name)!=sha(data):raise ValueError('installed policy differs')
            board.command('sh -n $d/'+name)
        r['service_links']=board.command('ls -l /etc/rc5.d/*xserver*')
        board.command('z=/etc/init.d/.p44-switch');board.command('test ! -e $z');board.command('cp $d/boot $z');board.command('chmod 755 $z')
        if digest('/etc/init.d/.p44-switch')!=sha(files['boot']):raise ValueError('policy staging differs')
        r['status']='verified_service_policy_install_intent';save();board.command('mv $z /etc/init.d/xserver-nodm');r['service_wrapper_installed']=True;save()
        board.command('sync',timeout=20);board.command('/etc/init.d/xserver-nodm start',timeout=25)
        r['consoleblank']=board.value('/sys/module/kernel/parameters/consoleblank');r['PWM_after']=board.command('cat /sys/kernel/debug/pwm')
        r['processes_after']=board.command('ps -eww -o pid,ppid,args')
        if r['consoleblank']!='0' or not re.search(r'pwm-2.*requested enabled.*duty: 50000 ns',r['PWM_after']):raise ValueError('wake interfaces did not apply')
        if re.search(r'(?m)^\s*\d+\s+\d+\s+(?:/\S*/)?(?:Xorg|xinit)(?:\s|$)',r['processes_after']):raise ValueError('desktop X owner remains')
        if digest('/etc/init.d/xserver-nodm')!=sha(files['boot']) or digest(d+'/xserver-original')!=sha(original):raise ValueError('policy/backup changed')
        r['status']='conditional_X_policy_installed_desktop_stopped_console_unblanked'
    except Exception as e:r.update(status='failed_or_unconfirmed',error=repr(e))
    finally:
        if board:board.close()
        r['serial_closed']=True;save();print(out);print(r['status'])
    return 0 if r['status'].startswith('conditional_') else 1
if __name__=='__main__':raise SystemExit(main())
