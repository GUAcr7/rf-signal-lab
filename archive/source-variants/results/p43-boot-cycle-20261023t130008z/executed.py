"""One persistent-profile reboot, board-started P42 RX, owned stop, pause for archiving.

No hot PL/overlay operations. Stop on the first failed gate; no reboot retry.
Restoring original S99 after a successful stop deliberately pauses future startup.
"""
import argparse
from datetime import datetime,timezone
import hashlib,json,math,re,time
from pathlib import Path
import xml.etree.ElementTree as ET
from p32_session import ROOT
from p35_once_merged_trial import TrialConsole,validate_inputs,verified_reuse,FACTORY,OVERLAY_HASHES,RF_NAMES
from p35_uart_files import upload
from p36_full_rx_run import RF_EXPECTED,CRITICAL_KERNEL
from p36_fb_snapshot_run import accepted_panel_parent
from p39_run_latest_panel import validate_summary
from p42_run_live_panel import validate_progress
from p43_boot_templates import render,WORK
from p37_review_archives import archive_bytes

def sha(b):return hashlib.sha256(b).hexdigest()
def read(p):return json.loads(p.read_text('utf-8'))

def installed_snapshot(previous,source):
    """Explicit archived source, including cold cycles with no files/ copy."""
    snapshot=read(source)
    if (snapshot.get('status')!='passed_long_running_RX_LCD_progress_and_independent_idle'
        or not snapshot.get('serial_closed')
        or snapshot.get('installed_directory')!=previous['installed_directory']
        or snapshot.get('installed_files_sha256')!=previous['installed_files_sha256']):
        raise ValueError('artifact cycle must match the exact installed profile')
    files={}
    for name,digest in previous['installed_files_sha256'].items():
        if not re.fullmatch(r'[a-z-]+',name):raise ValueError('invalid artifact filename')
        data=(source.parent/'files'/name).read_bytes()
        if sha(data)!=digest:raise ValueError('previous install changed')
        files[name]=data
    return files

def main():
    p=argparse.ArgumentParser(description=__doc__)
    group=p.add_mutually_exclusive_group(required=True)
    group.add_argument('--suite-report',type=Path)
    group.add_argument('--candidate-suite',type=Path)
    p.add_argument('--build-report',type=Path)
    p.add_argument('--current-status-report',type=Path)
    p.add_argument('--boot-observation',type=Path)
    p.add_argument('--boot-review',type=Path)
    p.add_argument('--validate-only',action='store_true',help='host gates and rendered bytes only; never open a port')
    p.add_argument('--preparation-report',type=Path,required=True)
    p.add_argument('--reuse-cycle',type=Path)
    p.add_argument('--reuse-review',type=Path)
    p.add_argument('--artifact-cycle',type=Path)
    p.add_argument('--observe-seconds',type=int,default=20,choices=range(20,901),metavar='20..900')
    args=p.parse_args()
    if args.candidate_suite:
        if not args.build_report or not args.current_status_report:p.error('candidate migration requires explicit build and current status reports')
        from p49_candidate_gate import validate_candidate
        suite,checked_boot=validate_candidate(args.candidate_suite,args.build_report,args.current_status_report,args.reuse_cycle,args.boot_observation,args.boot_review)
        args.suite_report=args.candidate_suite
    else:
        if args.build_report or args.current_status_report or args.boot_observation or args.boot_review:p.error('explicit build/status/observation supported only with a candidate suite')
        suite=read(args.suite_report)
        if suite['status']!='passed_short_until_signal_stop_restart_10min_and_archived_review' or not suite['independent_final_idle_verified'] or not suite['serial_closed']:raise ValueError('accepted P42 suite required')
    for stage in suite['stages']:
        source=Path(stage['report']);source=source if source.is_absolute() else ROOT/source
        if sha(source.read_bytes())!=stage['report_sha256']:raise ValueError('suite evidence changed')
    prep=read(args.preparation_report)
    if prep['status']!='passed_persistent_shell_and_stop_gates_not_hardware_boot' or prep['test_count']!=13 or not prep['input_hashes_unchanged']:raise ValueError('accepted shell preparation required')
    for path,digest in prep['inputs_sha256'].items():
        if sha((ROOT/path).read_bytes())!=digest:raise ValueError('tested source changed '+path)
    xml=Path(prep['test_xml']);cases=list(ET.parse(xml).getroot().iter('testcase'))
    if sha(xml.read_bytes())!=prep['test_xml_sha256'] or len(cases)!=13 or any(list(c.iter(t)) for c in cases for t in ('failure','error','skipped')):raise ValueError('shell proof changed')
    merged=ROOT/'results/p35-once-merged-20261022T022336Z/report.json';prior=read(merged)
    bp=Path(prior['bitstream_report']);op=Path(prior['overlay_report'])
    bit,overlay,binary,dtbo=validate_inputs(bp,op);reuse=verified_reuse(merged,bp,op,binary,dtbo)
    build_path=args.build_report or ROOT/'results/p42-build-20261022T022745Z/report.json';build=read(build_path)
    if build['schema']!='rfsig.p42_build.v1' or build['status']!='passed_native_mock_tests_and_ARM_build_not_board_test' or build['test_count']<21 or not all(build['target_checks'].values()):raise ValueError('P42 build not accepted')
    for path,digest in build['inputs_sha256'].items():
        if sha((ROOT/path).read_bytes())!=digest:raise ValueError('native input changed')
    monitor=Path(build['binary']).read_bytes()
    if sha(monitor)!=build['binary_sha256']:raise ValueError('monitor changed')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');directory='/etc/p43-'+stamp
    boot=checked_boot if args.candidate_suite else suite['expected_boot'];bit_path='/lib/firmware/'+reuse['firmware_name'];dtbo_path='/lib/firmware/'+reuse['overlay_name']
    files=render(directory,boot,sha(monitor),bit_path,sha(binary),dtbo_path,sha(dtbo));files['monitor']=monitor
    if args.reuse_cycle:
        if not args.reuse_review:p.error('archive and independent review required before another reboot')
        previous=read(args.reuse_cycle)
        if not accepted_panel_parent(previous,previous['expected_boot']) or previous.get('startup_profile')!='p43' or not previous.get('startup_paused_for_archiving'):raise ValueError('accepted paused preceding cycle required')
        review=read(args.reuse_review)
        if review['status']!='passed_P42_archives_and_independent_NumPy' or Path(review['trial']).resolve()!=args.reuse_cycle.resolve() or review['expected_boot']!=previous['expected_boot']:raise ValueError('preceding cycle review differs')
        for stage in review['stages']:
            if sha(Path(stage['report']).read_bytes())!=stage['report_sha256']:raise ValueError('previous review evidence changed')
            if stage['label'].endswith('_archive'):archive_bytes(Path(stage['report']))
        boot=previous['expected_boot'];directory=previous['installed_directory']
        files=installed_snapshot(previous,args.artifact_cycle or args.reuse_cycle)
        if files['monitor']!=monitor:raise ValueError('reused monitor differs')
    if args.validate_only:
        out=ROOT/'results'/('p49-migration-preflight-'+stamp);out.mkdir(exist_ok=False)
        inputs={k:dict(path=str(v.resolve()),sha256=sha(v.read_bytes())) for k,v in vars(args).items() if isinstance(v,Path)}
        result=dict(status='passed_host_migration_gates_not_board_test',inputs=inputs,armed_boot=boot,
            display_revision=build.get('display_revision','p42'),binary_sha256=sha(monitor),
            rendered_files_sha256={k:sha(v) for k,v in files.items()},
            board_operations=False,UART_opened=False,reboots_issued=0,persistent_native_replaced=False)
        (out/'report.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        (out/'executed.py').write_bytes(Path(__file__).read_bytes())
        print(out);print(result['status']);return 0
    out=ROOT/'results'/('p43-boot-cycle-'+stamp);out.mkdir(exist_ok=False);(out/'files').mkdir()
    for name,data in files.items():(out/'files'/name).write_bytes(data)
    r=dict(schema='rfsig.p42_board.v1',status='preflight',startup_profile='p43',stages=[],armed_boot=boot,expected_boot=None,
        installed_directory=directory,installed_files_sha256={k:sha(v) for k,v in files.items()},
        suite_report=str(args.suite_report.resolve()),suite_report_sha256=sha(args.suite_report.read_bytes()),
        preparation_report=str(args.preparation_report.resolve()),preparation_report_sha256=sha(args.preparation_report.read_bytes()),
        build_report=str(build_path),binary_sha256=sha(monitor),RAM_directory=WORK,
        duration_ms=0,interval_ms=500,observation_seconds_requested=args.observe_seconds,progress_samples=[],reboots_issued=0,TX_operations=False,
        host_launches_monitor_after_boot=False,host_PL_or_overlay_commands_after_boot=False,
        startup_files_written=True,persistent_autostart_enabled=False,startup_paused_for_archiving=False,
        physical_LCD_animation_confirmed=False,lossless_proven=False,native_completion_unconfirmed=False)
    if args.reuse_cycle:r['reuse_cycle']=str(args.reuse_cycle.resolve())
    if args.candidate_suite:
        if boot!=checked_boot:raise ValueError('candidate startup boot differs')
        r.update(display_revision='p48',current_status_report=str(args.current_status_report.resolve()),
            current_status_report_sha256=sha(args.current_status_report.read_bytes()),cold_P48_verified=False)
        if args.boot_observation:
            r['current_boot_evidence']={k:dict(path=str(v.resolve()),sha256=sha(v.read_bytes())) for k,v in
                dict(observation=args.boot_observation,review=args.boot_review).items()}
    if args.artifact_cycle:r['artifact_cycle']=dict(path=str(args.artifact_cycle.resolve()),sha256=sha(args.artifact_cycle.read_bytes()))
    (out/'executed.py').write_bytes(Path(__file__).read_bytes())
    def save():
        (out/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
        (ROOT/'results/p43-active.json').write_text(json.dumps(dict(report=str(out/'report.json'),status=r['status'],wrapper_may_be_installed=r.get('wrapper_may_be_installed',False)),indent=2)+'\n',encoding='utf-8')
    def phase(s):r['status']=s;save();print(s,flush=True)
    board=None;guard_sha=sha(files['original']);wrapper_sha=sha(files['boot'])
    def digest(path):
        board.command('f='+path);found=re.findall(r'^([0-9a-f]{64})\s+\S+\r?$',board.command('sha256sum $f'),re.M)
        if len(found)!=1:raise ValueError('ambiguous hash')
        return found[0]
    def identity(expected):
        if 'Zynq-Tronlong' not in board.command('uname -a') or board.value('/proc/sys/kernel/random/boot_id')!=expected or board.value('/proc/sys/kernel/tainted')!='0':raise ValueError('board/boot/taint changed')
    def idle(expected,installed_sha):
        identity(expected)
        if digest('/etc/rcS.d/S99board')!=installed_sha or board.value('/etc/board-mode')!='rf':raise ValueError('guard/mode changed')
        if re.search(r'arm-latest|arm[-_]rx|arm[-_]panel|arm-tx-source|iio_readdev|/run/p42-\d+/monitor|/etc/p41-\S+/monitor',board.command('ps -ef')):raise ValueError('competing monitor')
        board.command('/etc/rcS.d/S99board --check-rf');board.command('ir=/sys/bus/iio/devices')
        text=board.command('for n in $ir/iio:device*;do echo $n;cat $n/name;done')
        pairs=re.findall(r'(/sys/bus/iio/devices/iio:device\d+)\r?\n([^\r\n]+)',text)
        if any(sum(n==name for _,n in pairs)!=1 for name in RF_NAMES):raise ValueError('missing/ambiguous RF')
        names={n:d for d,n in pairs};board.command('cd '+names['cf-ad9361-lpc'])
        if board.value('buffer/enable')!='0' or any(board.value('scan_elements/in_voltage'+str(i)+'_en')!='0' for i in range(4)):raise ValueError('RX not idle')
        board.command('cd '+names['ad9361-phy']);attributes={k:board.value(k) for k in RF_EXPECTED}
        if attributes!=RF_EXPECTED:raise ValueError('RF parameters differ')
        if re.search(CRITICAL_KERNEL,board.command('dmesg',timeout=25)):raise ValueError('kernel fault')
        return dict(boot=expected,taint='0',buffer='0',scans=['0']*4,attributes=attributes)
    def switch(name):
        board.command('j='+directory);board.command('z=/etc/rcS.d/.p43-switch');board.command('test ! -e $z')
        board.command('cp $j/'+name+' $z');board.command('chmod 755 $z')
        if digest('/etc/rcS.d/.p43-switch')!=sha(files[name]):raise ValueError('switch staging hash')
        r['guard_switch_intent']=name;save();board.command('mv $z /etc/rcS.d/S99board');board.command('sync',timeout=20)
        if digest('/etc/rcS.d/S99board')!=sha(files[name]):raise ValueError('installed guard differs')
        r['wrapper_may_be_installed']=name=='boot';save()
    save()
    try:
        board=TrialConsole('COM8',r,save,out);board.shell();r['armed_state']=idle(boot,guard_sha)
        for name,wanted in {**FACTORY,**OVERLAY_HASHES}.items():
            if name!='system_wrapper.bin' and digest('/lib/firmware/'+name)!=wanted:raise ValueError('factory files changed')
        if digest(bit_path)!=sha(binary) or digest(dtbo_path)!=sha(dtbo):raise ValueError('cached safe pair differs')
        board.command('j='+directory)
        if not args.reuse_cycle:
            temp='/tmp/p35-p43-'+stamp[9:15];board.command('mkdir '+temp)
            for name,data in files.items():upload(board,temp+'/'+name,data)
            board.command('t='+temp);board.command('mkdir $j')
            for name in files:
                board.command('cp $t/'+name+' $j/'+name);board.command('chmod 755 $j/'+name)
        for name,data in files.items():
            if digest(directory+'/'+name)!=sha(data):raise ValueError('installed file hash differs '+name)
        for name in ('bringup','boot','control','run'):board.command('sh -n $j/'+name)
        board.command('test ! -e $j/disabled');board.command('test ! -e $j/pending')
        idle(boot,guard_sha);phase('arming_persistent_profile');switch('boot')
        phase('ordinary_reboot_board_startup_intent');board.port.write(b'reboot\r');r['reboots_issued']=1;r['native_completion_unconfirmed']=True;save()
        text=''
        for _ in range(2):
            text+=board.read(45,r'login:\s*$');(out/'boot-console.txt').write_text(text,encoding='utf-8')
            if re.search(r'login:\s*$',text):break
        if not re.search(r'U-Boot|Booting Linux|Linux version',text) or not re.search(r'login:\s*$',text):raise ValueError('new boot/login missing')
        board.shell();actual=board.value('/proc/sys/kernel/random/boot_id')
        if actual==boot:raise ValueError('fresh boot missing')
        identity(actual);r['expected_boot']=actual
        if digest('/etc/rcS.d/S99board')!=wrapper_sha:raise ValueError('persistent wrapper not retained')
        if board.value('/run/p43-init-boot')!=actual:raise ValueError('startup boot identity differs')
        board.command('j='+directory);board.command('test ! -e $j/pending');board.command('test ! -e $j/disabled')
        log=board.command('cat /run/p43-boot.log');(out/'startup-log.txt').write_text(log,encoding='utf-8')
        for marker in ('ORIGINAL_BACKUP_VERIFIED','EMPTY_BINDINGS_VERIFIED','PL_ATTEMPT=1','OVERLAY_ATTEMPT=1','MONITOR_LAUNCH','PERSISTENT_MONITOR_READY'):
            if len(re.findall(r'^p43: '+re.escape(marker)+r'(?:\s|\r?$)',log,re.M))!=1:raise ValueError('startup marker differs '+marker)
        if 'FAILED:' in log:raise ValueError('startup failed')
        if not re.search(r'^\S+ /run tmpfs \S+',board.command('cat /proc/mounts'),re.M):raise ValueError('/run not RAM')
        if digest(WORK+'/monitor')!=sha(monitor):raise ValueError('RAM monitor changed')
        r.update(RAM_filesystem_verified=True,monitor_started_by_board_init=True,fresh_empty_boot_verified=True,
            persistent_wrapper_retained_during_RX=True,PL_programming_attempts=1,overlay_apply_attempts=1)
        phase('board_started_RX_observe_then_owned_stop');board.command('x='+WORK);board.command('g=$x/data/progress.json')
        begin=time.monotonic()
        while time.monotonic()-begin<args.observe_seconds:
            values=[json.loads(s) for s in board.command('cat $g').splitlines() if s.startswith('{')]
            if len(values)!=1:raise ValueError('missing progress')
            value=validate_progress(values[0],0,r['progress_samples'][-1] if r['progress_samples'] else None)
            if value['state']!='running':raise ValueError('autonomous program not running')
            r['progress_samples'].append(value);save();print('Autonomous updates '+str(value['display_updates']),flush=True);time.sleep(5)
        board.command('sh $j/control stop',timeout=12);r['cancel_signal_sent']=True
        values=re.findall(r'^([0-9]+)\r?$',board.command('cat $x/exit'),re.M)
        if len(values)!=1 or int(values[0]) not in (0,143):raise ValueError('native completion unknown')
        r.update(launcher_exit_code=int(values[0]),native_completion_unconfirmed=False)
        sizes=re.findall(r'^__N__(\d+)__E__\r?$',board.command('echo __N__$(wc -c <$x/log)__E__'),re.M)
        if len(sizes)!=1 or not 0<int(sizes[0])<=4096:raise ValueError('unbounded native log')
        output=board.command('cat $x/log');(out/'program.txt').write_text(output,encoding='utf-8')
        rows=[json.loads(s) for s in output.splitlines() if s.startswith('{')]
        summaries=[json.loads(s) for s in board.command('cat $x/data/summary.json').splitlines() if s.startswith('{')]
        if len(summaries)!=1:raise ValueError('summary missing')
        s=validate_summary(summaries[0],0,500,True)
        if s.get('program_version')!='p42' or s.get('progress_commits')!=s['display_updates']+1:raise ValueError('P42 summary differs')
        if args.candidate_suite and s.get('display_revision')!='p48':raise ValueError('candidate display revision differs')
        metrics=[v for v in rows if v.get('schema')=='rfsig.arm_panel_metrics.v2'];frames=[v for v in rows if v.get('schema')=='rfsig.latest_frame.v1']
        if len(rows)!=2 or len(metrics)!=1 or len(frames)!=1:raise ValueError('expected last frame only')
        if metrics[0]['iteration']!=s['display_updates']-1 or metrics[0]['analyse_only'] or metrics[0]['draw_ms']<=0 or frames[0]['source_block_sequence']!=s['last_display_sequence']:raise ValueError('last frame differs')
        final=[json.loads(line) for line in board.command('cat $g').splitlines() if line.startswith('{')]
        if len(final)!=1:raise ValueError('final progress missing')
        validate_progress(final[0],0,r['progress_samples'][-1])
        for key in ('display_updates','published_prefixes','consumed_prefixes','last_display_sequence','UI_overwritten_prefixes'):
            if final[0][key]!=s[key]:raise ValueError('final progress differs')
        if final[0]['state']!='stopped':raise ValueError('not cleanly stopped')
        r['progress_samples'].append(final[0]);r.update(native_summary=s,frame_metrics=metrics,source_frames=frames,
            native_log_bytes=int(sizes[0]),bounded_native_log_verified=True,native_progress_final_verified=True)
        r['after']=idle(actual,wrapper_sha);phase('stopped_independently_idle_pause_startup_for_archives');switch('original')
        r.update(startup_paused_for_archiving=True,persistent_autostart_enabled=False,guard_restored=True)
        raw=WORK+'/data/last-display-packed.bin';r.update(raw_sha256=digest(raw),raw_bytes=32768)
        board.command('x='+WORK);board.command('r='+raw);board.command('z=$r.gz');board.command('test ! -e $z');board.command('gzip -1 -c $r >$z')
        r.update(remote=raw+'.gz',compressed_sha256=digest(raw+'.gz'))
        values=re.findall(r'^__N__(\d+)__E__\r?$',board.command('echo __N__$(wc -c <$z)__E__'),re.M)
        if len(values)!=1:raise ValueError('compressed size ambiguous')
        r.update(compressed_bytes=int(values[0]),independent_final_idle_verified=True)
        idle(actual,guard_sha)
        hardware=dict(status='passed_fresh_boot_merged_probe_and_software_clocks_only',held_boot=actual,guard_restored=True,
            fresh_empty_boot_verified=True,reboots_issued=1,PL_programming_attempts=1,overlay_apply_attempts=1,
            overlay_apply_returned=True,serial_closed=True,bitstream_report=str(bp),bitstream_report_sha256=sha(bp.read_bytes()),
            overlay_report=str(op),overlay_report_sha256=sha(op.read_bytes()),startup_evidence=str(out/'report.json'),
            guard_restored_by_host_after_clean_stop=True,physical_PCLK_measured=False)
        (out/'hardware-trial.json').write_text(json.dumps(hardware,indent=2)+'\n',encoding='utf-8');r['hardware_trial']=str(out/'hardware-trial.json')
        r['status']='passed_long_running_RX_LCD_progress_and_independent_idle'
    except Exception as e:
        r.update(status='failed_or_state_unconfirmed',error=repr(e))
        if board:
            try:r['passive_tail']=board.read(3)
            except Exception as tail:r['passive_tail_error']=repr(tail)
    finally:
        if board:board.close()
        r.update(serial_closed=True,ended_utc=datetime.now(timezone.utc).isoformat());save()
    print(out);print(r['status']);return 0 if r['status'].startswith('passed_') else 1
if __name__=='__main__':raise SystemExit(main())
