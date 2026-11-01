"""Rearm the exact persistent profile after two archived, independently reviewed boots.

Writes startup selection only; current RX stays idle and no reboot/PL/TX occurs.
"""
import argparse
from datetime import datetime,timezone
import hashlib,json,re
from pathlib import Path
from p32_session import ROOT
from p35_once_merged_trial import TrialConsole,RF_NAMES,FACTORY,OVERLAY_HASHES
from p36_full_rx_run import RF_EXPECTED,CRITICAL_KERNEL
from p36_fb_snapshot_run import accepted_panel_parent
from p37_review_archives import archive_bytes

def sha(b):return hashlib.sha256(b).hexdigest()
def read(p):return json.loads(p.read_text('utf-8'))

def reviewed(cycle_path,review_path,require_clock=True):
    c=read(cycle_path);r=read(review_path)
    if (c.get('startup_profile')!='p43' or not accepted_panel_parent(c,c['expected_boot'])
        or not c['startup_paused_for_archiving'] or not c['monitor_started_by_board_init']
        or not c['persistent_wrapper_retained_during_RX'] or c['host_launches_monitor_after_boot']
        or c['host_PL_or_overlay_commands_after_boot']):raise ValueError('autonomous stopped cycle required')
    if r['status']!='passed_P42_archives_and_independent_NumPy' or Path(r['trial']).resolve()!=cycle_path.resolve() or r['trial_sha256']!=sha(cycle_path.read_bytes()):raise ValueError('matching completed review required')
    for stage in r['stages']:
        if stage['exit_code']!=0 or sha(Path(stage['report']).read_bytes())!=stage['report_sha256']:raise ValueError('review child changed')
        if stage['label'].endswith('_archive'):archive_bytes(Path(stage['report']))
    if (require_clock and not r.get('post_clock_acceptance')) or not r.get('screen_png'):raise ValueError('post clock and screen required')
    final=read(Path(r['final_review']))
    if not all(final['checks'].values()):raise ValueError('independent numerical check failed')
    return c,r

def current_warm_matches(previous,current):
    if (current.get('reboots_issued')!=1 or not current.get('fresh_empty_boot_verified')
        or current.get('startup_origin')=='user_confirmed_power_cycle'
        or current['expected_boot']==previous['expected_boot']
        or current['installed_directory']!=previous['installed_directory']
        or current['installed_files_sha256']!=previous['installed_files_sha256']):
        raise ValueError('new reviewed warm boot must retain the exact profile')
    return current

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('cycle-one','review-one','cycle-two','review-two'):p.add_argument('--'+name,type=Path,required=True)
    for name in ('current-cycle','current-review','current-clock'):p.add_argument('--'+name,type=Path)
    for name in ('current-warm-cycle','current-warm-review'):p.add_argument('--'+name,type=Path)
    args=p.parse_args();one,review1=reviewed(args.cycle_one,args.review_one);two,review2=reviewed(args.cycle_two,args.review_two)
    if (one['expected_boot']==two['expected_boot'] or two['armed_boot']!=one['expected_boot']
        or Path(two['reuse_cycle']).resolve()!=args.cycle_one.resolve()
        or one['installed_directory']!=two['installed_directory'] or one['installed_files_sha256']!=two['installed_files_sha256']):raise ValueError('two matching sequential fresh boots required')
    cold_verified=False
    if any((args.current_warm_cycle,args.current_warm_review)):
        if not all((args.current_warm_cycle,args.current_warm_review)) or any((args.current_cycle,args.current_review,args.current_clock)):
            p.error('one complete current warm pair or cold triple required')
        warm,_=reviewed(args.current_warm_cycle,args.current_warm_review)
        two=current_warm_matches(two,warm)
    if any((args.current_cycle,args.current_review,args.current_clock)):
        if not all((args.current_cycle,args.current_review,args.current_clock)):p.error('all current cold-cycle reports required')
        cold,_=reviewed(args.current_cycle,args.current_review,require_clock=False);clock=read(args.current_clock)
        if (cold.get('startup_origin')!='user_confirmed_power_cycle' or cold['reboots_issued']!=0 or cold['power_cycles_observed']!=1
            or cold['installed_directory']!=two['installed_directory'] or cold['installed_files_sha256']!=two['installed_files_sha256']
            or clock['status']!='passed_user_power_cycle_gated_clock_driver_register_consistency'
            or clock['boot_id']!=cold['expected_boot'] or clock['trial_sha256']!=sha(args.current_cycle.read_bytes())
            or Path(clock['trial']).resolve()!=args.current_cycle.resolve()):raise ValueError('matching cold power-cycle and clock acceptance required')
        two=cold;cold_verified=True
    directory=two['installed_directory']
    if not re.fullmatch(r'/etc/p43-\d{8}T\d{6}Z',directory):raise ValueError('installed directory')
    files={name:(args.cycle_two.parent/'files'/name).read_bytes() for name in two['installed_files_sha256']}
    if any(sha(data)!=two['installed_files_sha256'][name] for name,data in files.items()):raise ValueError('installed source bytes changed')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p43-enabled-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    r=dict(schema='rfsig.p43_enable.v1',status='preflight',stages=[],expected_boot=two['expected_boot'],installed_directory=directory,
        inputs={k:dict(path=str(v.resolve()),sha256=sha(v.read_bytes())) for k,v in vars(args).items() if v},
        installed_files_sha256=two['installed_files_sha256'],RX_operations=False,PL_changes=False,reboots_issued=0,TX_operations=False,
        startup_wrapper_installed=False,persistent_autostart_enabled=False,current_monitor_running=False,
        true_power_cycle_verified=cold_verified,PRODUCT_ID_FF_root_cause_closed=False,ADC_gaps='unknown',lossless_proven=False)
    (out/'executed.py').write_bytes(Path(__file__).read_bytes())
    def save():(out/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    board=None
    def digest(path):
        board.command('f='+path);v=re.findall(r'^([0-9a-f]{64})\s+\S+\r?$',board.command('sha256sum $f'),re.M)
        if len(v)!=1:raise ValueError('ambiguous hash')
        return v[0]
    def idle(expected_guard):
        if board.value('/proc/sys/kernel/random/boot_id')!=two['expected_boot'] or board.value('/proc/sys/kernel/tainted')!='0' or 'Zynq-Tronlong' not in board.command('uname -a'):raise ValueError('board/boot/taint changed')
        if digest('/etc/rcS.d/S99board')!=expected_guard or board.value('/etc/board-mode')!='rf':raise ValueError('guard/mode changed')
        if re.search(r'/run/p42-\d+/monitor|arm-latest|arm[-_]rx|arm[-_]panel|iio_readdev|arm-tx-source',board.command('ps -ef')):raise ValueError('monitor active')
        board.command('/etc/rcS.d/S99board --check-rf');board.command('ir=/sys/bus/iio/devices')
        t=board.command('for n in $ir/iio:device*;do echo $n;cat $n/name;done')
        pairs=re.findall(r'(/sys/bus/iio/devices/iio:device\d+)\r?\n([^\r\n]+)',t)
        if any(sum(n==wanted for _,n in pairs)!=1 for wanted in RF_NAMES):raise ValueError('RF names differ')
        names={n:d for d,n in pairs};board.command('cd '+names['cf-ad9361-lpc'])
        if board.value('buffer/enable')!='0' or any(board.value('scan_elements/in_voltage'+str(i)+'_en')!='0' for i in range(4)):raise ValueError('RX not idle')
        board.command('cd '+names['ad9361-phy'])
        if {k:board.value(k) for k in RF_EXPECTED}!=RF_EXPECTED:raise ValueError('RF settings changed')
        if re.search(CRITICAL_KERNEL,board.command('dmesg',timeout=25)):raise ValueError('kernel fault')
    save()
    try:
        board=TrialConsole('COM8',r,save,out);board.shell();idle(sha(files['original']))
        for name,wanted in {**FACTORY,**OVERLAY_HASHES}.items():
            if name!='system_wrapper.bin' and digest('/lib/firmware/'+name)!=wanted:raise ValueError('factory files changed')
        board.command('j='+directory);board.command('test ! -e $j/disabled');board.command('test ! -e $j/pending')
        for name,data in files.items():
            if digest(directory+'/'+name)!=sha(data):raise ValueError('installed profile changed')
        board.command('z=/etc/rcS.d/.p43-switch');board.command('test ! -e $z');board.command('cp $j/boot $z');board.command('chmod 755 $z')
        if digest('/etc/rcS.d/.p43-switch')!=sha(files['boot']):raise ValueError('wrapper staging mismatch')
        r['status']='verified_persistent_enable_intent';save();board.command('mv $z /etc/rcS.d/S99board')
        r['startup_wrapper_installed']=True;save();board.command('sync',timeout=20);idle(sha(files['boot']))
        r.update(status='passed_persistent_profile_rearmed_after_two_archived_warm_boots',
            persistent_autostart_enabled=True,current_RX_idle_verified=True,software_reboot_cycles_verified=2,
            wrapper_sha256=sha(files['boot']),original_guard_sha256=sha(files['original']),native_duration_ms=0,
            timeout_safety_limit_s=86400,current_monitor_running=False,default_mode='rf')
    except Exception as e:r.update(status='failed_or_state_unconfirmed',error=repr(e))
    finally:
        if board:board.close()
        r['serial_closed']=True;r['ended_utc']=datetime.now(timezone.utc).isoformat();save()
    print(out);print(r['status']);return 0 if r['status'].startswith('passed_') else 1
if __name__=='__main__':raise SystemExit(main())
