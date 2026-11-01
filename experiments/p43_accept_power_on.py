"""Observe and stop user-powered P43 boot; preserve actual counts and no host reboot."""
import argparse
from datetime import datetime,timezone
import hashlib,json,re,time
from pathlib import Path
from p32_session import ROOT
from p35_once_merged_trial import TrialConsole,RF_NAMES
from p36_full_rx_run import RF_EXPECTED,CRITICAL_KERNEL
from p39_run_latest_panel import validate_summary
from p42_run_live_panel import validate_progress

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text('utf-8'))
def observed_origin(enable,before,capture,human,console):
    """An existing new boot alone never proves a physical power cycle."""
    boot=before['boot_id']
    if boot==enable['expected_boot']:raise ValueError('a new boot is required')
    if capture is None and human is None:
        log=before['startup_log']
        if not before.get('init_boot_marker_matches'):raise ValueError('startup identity marker missing')
        for marker in ('ORIGINAL_BACKUP_VERIFIED','EMPTY_BINDINGS_VERIFIED','PL_ATTEMPT=1','OVERLAY_ATTEMPT=1','MONITOR_LAUNCH','PERSISTENT_MONITOR_READY'):
            if len(re.findall(r'^p43: '+re.escape(marker)+r'(?:\s|\r?$)',log,re.M))!=1:raise ValueError('startup marker differs '+marker)
        if not re.search(r'ORIGINAL_BACKUP_VERIFIED boot='+re.escape(boot),log):raise ValueError('startup log boot differs')
        return 'existing_new_boot_power_cycle_not_verified'
    if capture is None or human is None:raise ValueError('both human and passive evidence required')
    if not human.get('new_board_powercycled_by_user') or human['old_boot']!=enable['expected_boot']:raise ValueError('user-reported power cycle required')
    if capture['status']!='passive_window_completed' or capture['UART_bytes_sent']!=0 or not capture['new_kernel_output_observed'] or not capture['P43_ready_marker_observed']:raise ValueError('passive startup evidence required')
    if not re.search(r'ORIGINAL_BACKUP_VERIFIED boot='+re.escape(boot),console):raise ValueError('captured boot differs')
    return 'user_confirmed_power_cycle'

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('enable-report','status-before'):p.add_argument('--'+name,type=Path,required=True)
    for name in ('passive-capture','human-event'):p.add_argument('--'+name,type=Path)
    p.add_argument('--observed-only',action='store_true')
    p.add_argument('--minimum-running-seconds',type=int,choices=range(0,901),default=0,metavar='0..900')
    args=p.parse_args();enable=read(args.enable_report);before=read(args.status_before)
    if args.observed_only:
        if args.passive_capture or args.human_event:p.error('observed-only cannot claim a power cycle')
        capture=human=None;console=''
    else:
        if not args.passive_capture or not args.human_event:p.error('passive and human power-cycle evidence required')
        capture=read(args.passive_capture);human=read(args.human_event);console=(args.passive_capture.parent/'console.txt').read_text('utf-8')
    boot=before['boot_id'];directory=enable['installed_directory']
    if (enable['status']!='passed_persistent_profile_rearmed_after_two_archived_warm_boots' or before['status']!='read_only_persistent_profile_state_collected'
        or not before['persistent_wrapper_selected'] or before['taint']!='0' or before['pending_present'] or before['disabled_present']
        or not before['native_process_observed'] or before['RX_buffer']!='1' or before['RX_scans']!=['1','1','0','0']):raise ValueError('autonomous running profile required')
    origin=observed_origin(enable,before,capture,human,console)
    prefix='p43-observed-cycle-' if args.observed_only else 'p43-cold-cycle-'
    out=ROOT/'results'/datetime.now(timezone.utc).strftime(prefix+'%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    r=dict(schema='rfsig.p42_board.v1',status='observing',stages=[],expected_boot=boot,startup_profile='p43',
        startup_origin=origin,reboots_issued=0,power_cycles_observed=0 if args.observed_only else 1,
        installed_directory=directory,installed_files_sha256=enable['installed_files_sha256'],RAM_directory='/run/p42-000043',
        inputs={k:dict(path=str(v.resolve()),sha256=sha(v)) for k,v in vars(args).items() if isinstance(v,Path)},
        minimum_running_seconds_requested=args.minimum_running_seconds,
        duration_ms=0,interval_ms=500,cancel_signal_sent=False,progress_samples=[before['native_progress']],
        host_launches_monitor_after_boot=False,host_PL_or_overlay_commands_after_boot=False,
        TX_operations=False,startup_paused_for_archiving=False,persistent_autostart_enabled=True,
        monitor_started_by_board_init=True,persistent_wrapper_retained_during_RX=True,fresh_empty_boot_verified=True,
        PL_programming_attempts=1,overlay_apply_attempts=1,native_completion_unconfirmed=True,
        physical_LCD_animation_confirmed=False,lossless_proven=False)
    if enable.get('display_revision')=='p48':
        r.update(display_revision='p48',binary_sha256=enable['installed_files_sha256']['monitor'])
    (out/'executed.py').write_bytes(Path(__file__).read_bytes())
    def save():(out/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    board=None
    def digest(path):
        board.command('f='+path);v=re.findall(r'^([0-9a-f]{64})\s+\S+\r?$',board.command('sha256sum $f'),re.M)
        if len(v)!=1:raise ValueError('ambiguous hash')
        return v[0]
    def idle(guard):
        if board.value('/proc/sys/kernel/random/boot_id')!=boot or board.value('/proc/sys/kernel/tainted')!='0' or digest('/etc/rcS.d/S99board')!=guard:raise ValueError('identity/guard/taint changed')
        if re.search(r'/run/p42-\d+/monitor|arm[-_]rx|arm[-_]panel|iio_readdev',board.command('ps -ef')):raise ValueError('receiver still running')
        board.command('ir=/sys/bus/iio/devices');t=board.command('for n in $ir/iio:device*;do echo $n;cat $n/name;done')
        pairs=re.findall(r'(/sys/bus/iio/devices/iio:device\d+)\r?\n([^\r\n]+)',t)
        if any(sum(n==name for _,n in pairs)!=1 for name in RF_NAMES):raise ValueError('RF names missing/duplicated')
        names={n:d for d,n in pairs};board.command('cd '+names['cf-ad9361-lpc'])
        if board.value('buffer/enable')!='0' or any(board.value('scan_elements/in_voltage'+str(i)+'_en')!='0' for i in range(4)):raise ValueError('RX not idle')
        board.command('cd '+names['ad9361-phy'])
        attributes={k:board.value(k) for k in RF_EXPECTED}
        if attributes!=RF_EXPECTED:raise ValueError('RF settings changed')
        if re.search(CRITICAL_KERNEL,board.command('dmesg',timeout=25)):raise ValueError('kernel fault')
        return dict(boot=boot,taint='0',buffer='0',scans=['0']*4,attributes=attributes)
    save()
    try:
        board=TrialConsole('COM8',r,save,out);board.shell()
        if board.value('/proc/sys/kernel/random/boot_id')!=boot or digest('/etc/rcS.d/S99board')!=enable['wrapper_sha256']:raise ValueError('new boot/guard changed')
        if enable.get('display_revision')=='p48':
            if digest('/run/p42-000043/monitor')!=r['binary_sha256']:raise ValueError('P48 RAM binary differs')
            board.command('ir=/sys/bus/iio/devices')
            text=board.command('for n in $ir/iio:device*;do echo $n;cat $n/name;done')
            pairs=re.findall(r'(/sys/bus/iio/devices/iio:device\d+)\r?\n([^\r\n]+)',text)
            if any(sum(n==name for _,n in pairs)!=1 for name in RF_NAMES):raise ValueError('RF names differ')
            board.command('cd '+dict((n,d) for d,n in pairs)['ad9361-phy'])
            attributes={k:board.value(k) for k in RF_EXPECTED}
            if attributes!=RF_EXPECTED:raise ValueError('P48 RF profile differs')
            r['before']=dict(boot=boot,attributes=attributes);save()
        board.command('j='+directory);board.command('x=/run/p42-000043');board.command('g=$x/data/progress.json')
        observed=0;deadline=time.monotonic()+args.minimum_running_seconds+60
        while observed<3 or r['progress_samples'][-1]['elapsed_software_s']<args.minimum_running_seconds:
            if time.monotonic()>deadline:raise ValueError('observation deadline reached')
            values=[json.loads(s) for s in board.command('cat $g').splitlines() if s.startswith('{')]
            if len(values)!=1:raise ValueError('progress missing')
            value=validate_progress(values[0],0,r['progress_samples'][-1])
            if value['state']!='running' or value['display_updates']<=r['progress_samples'][-1]['display_updates']:raise ValueError('no continued updates')
            r['progress_samples'].append(value);observed+=1;save();print('Autonomous updates '+str(value['display_updates']),flush=True);time.sleep(3)
        if digest(directory+'/control')!=enable['installed_files_sha256']['control']:raise ValueError('stop control changed')
        board.command('sh $j/control stop',timeout=12);r['cancel_signal_sent']=True
        v=re.findall(r'^([0-9]+)\r?$',board.command('cat $x/exit'),re.M)
        if len(v)!=1 or int(v[0]) not in (0,143):raise ValueError('completion unconfirmed')
        r.update(launcher_exit_code=int(v[0]),native_completion_unconfirmed=False)
        sizes=re.findall(r'^__N__(\d+)__E__\r?$',board.command('echo __N__$(wc -c <$x/log)__E__'),re.M)
        if len(sizes)!=1 or not 0<int(sizes[0])<=4096:raise ValueError('log bound failed')
        log=board.command('cat $x/log');(out/'program.txt').write_text(log,encoding='utf-8');rows=[json.loads(s) for s in log.splitlines() if s.startswith('{')]
        summaries=[json.loads(s) for s in board.command('cat $x/data/summary.json').splitlines() if s.startswith('{')]
        if len(summaries)!=1:raise ValueError('summary missing')
        s=validate_summary(summaries[0],0,500,True)
        if s.get('program_version')!='p42' or s.get('progress_commits')!=s['display_updates']+1:raise ValueError('P42 summary differs')
        if enable.get('display_revision')=='p48' and s.get('display_revision')!='p48':raise ValueError('P48 display revision differs')
        metrics=[v for v in rows if v.get('schema')=='rfsig.arm_panel_metrics.v2'];frames=[v for v in rows if v.get('schema')=='rfsig.latest_frame.v1']
        if len(rows)!=2 or len(metrics)!=1 or len(frames)!=1 or metrics[0]['iteration']!=s['display_updates']-1 or metrics[0]['analyse_only'] or frames[0]['source_block_sequence']!=s['last_display_sequence']:raise ValueError('last metrics/sequence differs')
        values=[json.loads(line) for line in board.command('cat $g').splitlines() if line.startswith('{')]
        if len(values)!=1 or values[0]['state']!='stopped':raise ValueError('final progress missing')
        validate_progress(values[0],0,r['progress_samples'][-1])
        if any(values[0][k]!=s[k] for k in ('display_updates','published_prefixes','last_display_sequence','consumed_prefixes','UI_overwritten_prefixes')):raise ValueError('final counts differ')
        r['progress_samples'].append(values[0]);r.update(native_summary=s,frame_metrics=metrics,source_frames=frames,
            native_log_bytes=int(sizes[0]),bounded_native_log_verified=True,native_progress_final_verified=True)
        if not re.search(r'^\S+ /run tmpfs \S+',board.command('cat /proc/mounts'),re.M):raise ValueError('/run not RAM')
        r['RAM_filesystem_verified']=True;r['after']=idle(enable['wrapper_sha256'])
        if digest(directory+'/original')!=enable['original_guard_sha256']:raise ValueError('rollback original changed')
        board.command('z=/etc/rcS.d/.p43-switch');board.command('test ! -e $z');board.command('cp $j/original $z');board.command('chmod 755 $z')
        if digest('/etc/rcS.d/.p43-switch')!=enable['original_guard_sha256']:raise ValueError('rollback staging mismatch')
        board.command('mv $z /etc/rcS.d/S99board');board.command('sync',timeout=20)
        r.update(guard_restored=True,startup_paused_for_archiving=True,persistent_autostart_enabled=False,startup_files_written=True)
        idle(enable['original_guard_sha256'])
        raw='/run/p42-000043/data/last-display-packed.bin';r.update(raw_sha256=digest(raw),raw_bytes=32768)
        board.command('r='+raw);board.command('z=$r.gz');board.command('test ! -e $z');board.command('gzip -1 -c $r >$z')
        r.update(remote=raw+'.gz',compressed_sha256=digest(raw+'.gz'))
        values=re.findall(r'^__N__(\d+)__E__\r?$',board.command('echo __N__$(wc -c <$z)__E__'),re.M)
        if len(values)!=1:raise ValueError('size ambiguous')
        r.update(compressed_bytes=int(values[0]),independent_final_idle_verified=True,status='passed_long_running_RX_LCD_progress_and_independent_idle')
    except Exception as e:r.update(status='failed_or_unconfirmed',error=repr(e))
    finally:
        if board:board.close()
        r['serial_closed']=True;save()
    print(out);print(r['status']);return 0 if r['status'].startswith('passed_') else 1
if __name__=='__main__':raise SystemExit(main())
