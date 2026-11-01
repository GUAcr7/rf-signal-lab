"""Read a pinned persistent profile without starting/stopping RX or changing startup."""
import argparse
from datetime import datetime,timezone
import hashlib,json,re
from pathlib import Path
from p32_session import ROOT
from p35_once_merged_trial import TrialConsole

def sha(b):return hashlib.sha256(b).hexdigest()
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--enable-report',type=Path,required=True);args=p.parse_args()
    enable=json.loads(args.enable_report.read_text('utf-8'))
    if enable['status']!='passed_persistent_profile_rearmed_after_two_archived_warm_boots':raise ValueError('accepted enable report required')
    directory=enable['installed_directory']
    if not re.fullmatch(r'/etc/p43-\d{8}T\d{6}Z',directory):raise ValueError('profile directory')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p43-status-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    r=dict(status='reading',stages=[],enable_report=str(args.enable_report.resolve()),enable_report_sha256=sha(args.enable_report.read_bytes()),
        board_file_writes=False,RF_attribute_writes=False,PL_changes=False,reboots_issued=0)
    (out/'executed.py').write_bytes(Path(__file__).read_bytes())
    def save():(out/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    board=None
    def digest(path):
        board.command('f='+path);v=re.findall(r'^([0-9a-f]{64})\s+\S+\r?$',board.command('sha256sum $f'),re.M)
        if len(v)!=1:raise ValueError('ambiguous SHA')
        return v[0]
    save()
    try:
        board=TrialConsole('COM8',r,save,out);board.shell()
        if 'Zynq-Tronlong' not in board.command('uname -a'):raise ValueError('wrong board')
        r.update(boot_id=board.value('/proc/sys/kernel/random/boot_id'),taint=board.value('/proc/sys/kernel/tainted'),mode=board.value('/etc/board-mode'))
        actual=digest('/etc/rcS.d/S99board');r['installed_guard_sha256']=actual
        if actual not in (enable['wrapper_sha256'],enable['original_guard_sha256']):raise ValueError('unknown startup guard')
        r['persistent_wrapper_selected']=actual==enable['wrapper_sha256']
        for name,wanted in enable['installed_files_sha256'].items():
            if digest(directory+'/'+name)!=wanted:raise ValueError('installed profile changed '+name)
        board.command('j='+directory)
        for name in ('pending','disabled'):
            t=board.command('if test -e $j/'+name+';then echo YES;else echo NO;fi')
            v=re.findall(r'^(YES|NO)\r?$',t,re.M)
            if len(v)!=1:raise ValueError('ambiguous latch')
            r[name+'_present']=v[0]=='YES'
        board.command('g=/run/p43-init-boot')
        t=board.command('if test -f $g;then cat $g;fi');r['init_boot_marker_matches']=r['boot_id'] in t
        board.command('g=/run/p43-boot.log');r['startup_log']=board.command('if test -f $g;then cat $g;fi')
        board.command('g=/run/p42-000043/data/progress.json')
        values=[json.loads(s) for s in board.command('if test -f $g;then cat $g;fi').splitlines() if s.startswith('{')]
        if len(values)>1:raise ValueError('ambiguous progress')
        r['native_progress']=values[0] if values else None
        processes=board.command('ps -ef');r['native_process_observed']=bool(re.search(r'/run/p42-000043/monitor',processes))
        r['kernel_tail']=board.command('dmesg | tail -n 160')
        board.command('ir=/sys/bus/iio/devices');t=board.command('for n in $ir/iio:device*;do echo $n;cat $n/name;done')
        names={n:d for d,n in re.findall(r'(/sys/bus/iio/devices/iio:device\d+)\r?\n([^\r\n]+)',t)};r['IIO_names']=names
        if 'cf-ad9361-lpc' in names:
            board.command('cd '+names['cf-ad9361-lpc']);r['RX_buffer']=board.value('buffer/enable')
            r['RX_scans']=[board.value('scan_elements/in_voltage'+str(i)+'_en') for i in range(4)]
        if board.value('/proc/sys/kernel/random/boot_id')!=r['boot_id']:raise ValueError('boot changed during reads')
        r['status']='read_only_persistent_profile_state_collected'
    except Exception as e:r.update(status='failed_or_unconfirmed',error=repr(e))
    finally:
        if board:board.close()
        r['serial_closed']=True;save();print(out);print(r['status'])
    return 0 if r['status'].startswith('read_only_') else 1
if __name__=='__main__':raise SystemExit(main())
