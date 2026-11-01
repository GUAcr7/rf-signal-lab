"""One self-restoring autonomous merged boot, finite RX/LCD, no permanent default change."""
import argparse
from datetime import datetime,timezone
import hashlib,json,math,re,time
from pathlib import Path
import xml.etree.ElementTree as ET

from p32_session import ROOT
from p35_once_merged_trial import TrialConsole,validate_inputs,verified_reuse,FACTORY,OVERLAY_HASHES,RF_NAMES
from p35_uart_files import upload
from p36_full_rx_run import RF_EXPECTED,CRITICAL_KERNEL
from p37_review_archives import archive_bytes
from p39_run_latest_panel import validate_summary
from p40_factory_boot import ACTIVE
from p41_boot_templates import render_runtime,render_boot


def sha(data):return hashlib.sha256(data).hexdigest()
def read(path):return json.loads(path.read_text('utf-8'))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('suite-report','bitstream-report','overlay-report','reuse-trial','build-report','preparation-report'):
        p.add_argument('--'+name,type=Path,required=True)
    args=p.parse_args();suite=read(args.suite_report)
    if suite['status']!='passed_fresh_boot_cancel_restart_120s_RX_LCD_and_archived_NumPy_review' or not suite['final_idle_verified'] or not suite['serial_closed']:
        raise ValueError('accepted idle recovery suite required')
    for stage in suite['stages']:
        path=Path(stage['report'])
        if sha(path.read_bytes())!=stage['report_sha256']:raise ValueError('suite input changed')
        if stage['label'].endswith('_archive'):archive_bytes(path)
    preparation=read(args.preparation_report)
    if preparation['status']!='passed_actual_shell_gates_and_template_syntax_not_board_boot' or preparation['test_count']!=8 or preparation['input_hashes_unchanged'] is not True:
        raise ValueError('accepted source-pinned shell preparation required')
    for path,digest in preparation['inputs_sha256'].items():
        if sha((ROOT/path).read_bytes())!=digest:raise ValueError('tested startup source changed')
    shell_tests=Path(preparation['test_xml'])
    if sha(shell_tests.read_bytes())!=preparation['test_xml_sha256']:raise ValueError('shell test results changed')
    cases=list(ET.parse(shell_tests).getroot().iter('testcase'))
    if len(cases)!=8 or any(list(c.iter(tag)) for c in cases for tag in ('failure','error','skipped')):
        raise ValueError('all eight actual shell tests must pass')
    bit,overlay,binary,dtbo=validate_inputs(args.bitstream_report,args.overlay_report)
    reuse=verified_reuse(args.reuse_trial,args.bitstream_report,args.overlay_report,binary,dtbo)
    build=read(args.build_report)
    if build['status']!='passed_native_mock_tests_and_ARM_build_not_board_test' or build['test_count']<18 or not all(build['target_checks'].values()):raise ValueError('unaccepted monitor build')
    for path,digest in build['inputs_sha256'].items():
        if sha((ROOT/path).read_bytes())!=digest:raise ValueError('monitor source changed')
    monitor=Path(build['binary']).read_bytes()
    if sha(monitor)!=build['binary_sha256']:raise ValueError('monitor binary changed')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out=ROOT/'results'/('p41-autonomous-once-'+stamp);out.mkdir(exist_ok=False)
    boot=suite['expected_boot'];directory='/etc/p41-'+stamp;ram='/tmp/p35-p41-'+stamp[9:15]
    work='/tmp/p35-p39-'+stamp[9:15];backup='/etc/p35-guard-'+stamp
    bit_path='/lib/firmware/'+reuse['firmware_name'];dtbo_path='/lib/firmware/'+reuse['overlay_name']
    guard=(ROOT/'board/boot/S99board').read_bytes();guard_sha=sha(guard)
    runtime=render_runtime(directory+'/monitor',sha(monitor),bit_path,sha(binary),dtbo_path,sha(dtbo),guard_sha,boot,work)
    wrapper=render_boot(backup,guard_sha,boot,directory+'/bringup',sha(runtime))
    r=dict(schema='rfsig.p41_autonomous_once.v1',status='preflight',stages=[],armed_boot=boot,
        expected_boot=None,held_boot=None,suite_report=str(args.suite_report.resolve()),
        bitstream_report=str(args.bitstream_report.resolve()),bitstream_report_sha256=sha(args.bitstream_report.read_bytes()),
        overlay_report=str(args.overlay_report.resolve()),overlay_report_sha256=sha(args.overlay_report.read_bytes()),
        bitstream_sha256=sha(binary),overlay_sha256=sha(dtbo),reuse_artifacts=reuse,
        build_report=str(args.build_report.resolve()),binary_sha256=sha(monitor),
        shell_tests=str(shell_tests.resolve()),shell_tests_sha256=sha(shell_tests.read_bytes()),
        preparation_report=str(args.preparation_report.resolve()),preparation_report_sha256=sha(args.preparation_report.read_bytes()),
        guard_sha256=guard_sha,runtime_sha256=sha(runtime),wrapper_sha256=sha(wrapper),
        installed_directory=directory,RAM_directory=work,backup=backup,
        reboots_issued=0,PL_programming_attempts=0,overlay_apply_attempts=0,
        guard_restored=False,fresh_empty_boot_verified=False,overlay_apply_returned=False,
        duration_ms=120000,interval_ms=500,cancel_signal_sent=False,
        host_launches_monitor_after_boot=False,host_PL_or_overlay_commands_after_boot=False,
        default_firmware_replaced=False,BOOT_or_base_DTB_modified=False,mode_modified=False,
        hot_overlay_removal=False,automatic_retry=False,TX_operations=False,
        temporary_startup_wrapper=True,persistent_autostart_enabled=False,
        physical_LCD_animation_confirmed=False,lossless_proven=False,
        native_completion_unconfirmed=False,PRODUCT_ID_FF_root_cause_closed=False)
    for name,data in [('executed.py',Path(__file__).read_bytes()),('runtime.sh',runtime),('boot.sh',wrapper),('monitor',monitor),
        ('build-report.json',args.build_report.read_bytes()),('suite-report.json',args.suite_report.read_bytes()),
        ('shell-tests.xml',shell_tests.read_bytes())]:(out/name).write_bytes(data)
    def save():(out/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    def phase(value):r['status']=value;save();print(value,flush=True)
    board=None;armed=False
    def digest(path):
        board.command('p='+path)
        values=re.findall(r'^([0-9a-f]{64})\s+\S+\r?$',board.command('sha256sum $p'),re.M)
        if len(values)!=1:raise ValueError('ambiguous SHA: '+path)
        return values[0]
    def identity(expected):
        if 'Zynq-Tronlong' not in board.command('uname -a') or board.value('/proc/sys/kernel/random/boot_id')!=expected or board.value('/proc/sys/kernel/tainted')!='0':raise ValueError('identity/taint changed')
    def factory_files():
        if board.value('/etc/board-mode')!='rf' or digest('/etc/rcS.d/S99board')!=guard_sha:raise ValueError('guard/mode changed')
        for name,wanted in {**FACTORY,**OVERLAY_HASHES}.items():
            if name!='system_wrapper.bin' and digest('/lib/firmware/'+name)!=wanted:raise ValueError('factory artifact changed')
        if digest('/lib/firmware/system_wrapper.bin') not in (FACTORY['system_wrapper.bin'],FACTORY['ad9361.bin']):raise ValueError('default staging changed')
    def idle(expected):
        identity(expected);factory_files()
        if re.search(ACTIVE+r'|/etc/p41-\d+T\d+Z/monitor',board.command('ps -ef')):raise ValueError('active experiment')
        board.command('/etc/rcS.d/S99board --check-rf');board.command('ir=/sys/bus/iio/devices')
        text=board.command('for d in $ir/iio:device*;do echo $d;cat $d/name;done')
        pairs=re.findall(r'(/sys/bus/iio/devices/iio:device\d+)\r?\n([^\r\n]+)',text)
        if any(sum(n==name for _,n in pairs)!=1 for name in RF_NAMES):raise ValueError('RF names missing/ambiguous')
        names={n:path for path,n in pairs};board.command('cd '+names['cf-ad9361-lpc'])
        if board.value('buffer/enable')!='0' or any(board.value('scan_elements/in_voltage'+str(i)+'_en')!='0' for i in range(4)):
            raise ValueError('RX active')
        board.command('cd '+names['ad9361-phy'])
        values={key:board.value(key) for key in RF_EXPECTED}
        if values!=RF_EXPECTED:raise ValueError('RF settings differ')
        if re.search(CRITICAL_KERNEL,board.command('dmesg',timeout=25)):raise ValueError('kernel fault')
        return dict(boot=expected,taint='0',buffer='0',scans=['0']*4,attributes=values)
    save()
    try:
        board=TrialConsole('COM8',r,save,out);board.shell();r['before']=idle(boot)
        for path,wanted in ((bit_path,sha(binary)),(dtbo_path,sha(dtbo))):
            if digest(path)!=wanted:raise ValueError('cached immutable artifact differs')
        board.command('test ! -e /etc/rcS.d/.p35-restore');board.command('mkdir '+ram)
        for name,data in [('monitor',monitor),('bringup',runtime),('boot',wrapper)]:upload(board,ram+'/'+name,data)
        board.command('t='+ram);board.command('sh -n $t/bringup');board.command('sh -n $t/boot')
        # Verify the installed BusyBox timeout does not reap a successful
        # init script's bounded background child when that script returns.
        probe=('#!/bin/sh\n(sleep 2; echo alive > '+ram+'/alive) </dev/null >/dev/null 2>&1 &\nexit 0\n').encode()
        upload(board,ram+'/probe',probe);board.command('timeout -k 1 1 sh $t/probe');board.command('sleep 3')
        if board.value(ram+'/alive')!='alive':raise ValueError('timeout background survival primitive failed')
        r['target_timeout_background_survival_verified']=True
        board.command('d='+directory);board.command('mkdir $d')
        for name,data in [('monitor',monitor),('bringup',runtime)]:
            board.command('cp $t/'+name+' $d/'+name);board.command('chmod 755 $d/'+name)
            if digest(directory+'/'+name)!=sha(data):raise ValueError('installed file differs')
        identity(boot);idle(boot)
        board.command('b='+backup);board.command('test ! -e $b');board.command('cp -p /etc/rcS.d/S99board $b')
        if digest(backup)!=guard_sha:raise ValueError('guard backup differs')
        board.command('t='+ram);board.command('u=/etc/rcS.d/.p41-once');board.command('test ! -e $u')
        board.command('cp $t/boot $u');board.command('chmod 755 $u')
        if digest('/etc/rcS.d/.p41-once')!=sha(wrapper):raise ValueError('wrapper differs')
        phase('verified_one_shot_autonomous_boot_arm_intent')
        board.command('mv $u /etc/rcS.d/S99board');armed=True
        if digest('/etc/rcS.d/S99board')!=sha(wrapper):raise ValueError('armed guard differs')
        board.command('sync',timeout=20);phase('ordinary_reboot_autonomous_init_intent')
        board.port.write(b'reboot\r');r['reboots_issued']=1;r['native_completion_unconfirmed']=True;save()
        text=''
        for _ in range(2):
            text+=board.read(45,r'login:\s*$');(out/'boot-console.txt').write_text(text,encoding='utf-8')
            if re.search(r'login:\s*$',text):break
        if not re.search(r'U-Boot|Booting Linux|Linux version',text) or not re.search(r'login:\s*$',text):raise ValueError('new boot/login missing')
        board.shell();actual=board.value('/proc/sys/kernel/random/boot_id')
        if actual==boot:raise ValueError('fresh boot absent')
        identity(actual);r.update(expected_boot=actual,held_boot=actual)
        if digest('/etc/rcS.d/S99board')!=guard_sha:raise ValueError('original guard not restored')
        r['guard_restored']=True;armed=False
        if board.value('/run/p35-hold-boot')!=actual:raise ValueError('hold identity missing')
        bootlog=board.command('cat /run/p41-boot.log');(out/'autonomous-boot-log.txt').write_text(bootlog,encoding='utf-8')
        for marker in ('ORIGINAL_GUARD_VERIFIED','EMPTY_BINDINGS_VERIFIED','PL_ATTEMPT=1','OVERLAY_ATTEMPT=1','MONITOR_LAUNCH','BOUNDED_MONITOR_LAUNCHED'):
            if len(re.findall(r'^p41: '+re.escape(marker)+r'(?:\s|\r?$)',bootlog,re.M))!=1:raise ValueError('startup marker missing/duplicated: '+marker)
        if 'p41: FAILED:' in bootlog:raise ValueError('autonomous startup failed')
        r.update(fresh_empty_boot_verified=True,PL_programming_attempts=1,overlay_apply_attempts=1,overlay_apply_returned=True,
            monitor_started_by_board_init=True)
        phase('autonomous_monitor_running_host_only_observes')
        board.command('x='+work);until=time.monotonic()+170
        while True:
            if time.monotonic()>until:raise ValueError('autonomous completion unknown')
            values=re.findall(r'^(WAIT|\d+)\r?$',board.command('if test -f $x/exit;then cat $x/exit;else echo WAIT;fi'),re.M)
            if len(values)!=1:raise ValueError('ambiguous completion')
            if values[0]!='WAIT':
                r['launcher_exit_code']=int(values[0]);r['native_completion_unconfirmed']=False;save()
                if values[0]!='0':raise ValueError('autonomous monitor failed')
                break
            time.sleep(2)
        output=board.command('cat $x/log',timeout=35);(out/'program.txt').write_text(output,encoding='utf-8')
        rows=[json.loads(line) for line in output.splitlines() if line.startswith('{')]
        values=[json.loads(line) for line in board.command('cat $x/data/summary.json').splitlines() if line.startswith('{')]
        if len(values)!=1:raise ValueError('summary missing')
        summary=validate_summary(values[0],120000,500)
        metrics=[v for v in rows if v.get('schema')=='rfsig.arm_panel_metrics.v2']
        frames=[v for v in rows if v.get('schema')=='rfsig.latest_frame.v1']
        if len(metrics)!=len(frames) or len(frames)!=summary['display_updates'] or len(rows)!=2*len(frames):raise ValueError('metric/frame count')
        prior=0
        for i,(metric,frame) in enumerate(zip(metrics,frames)):
            if metric['iteration']!=i or metric['analyse_only'] or metric['draw_ms']<=0 or metric['frames']!=8 or frame['update']!=i or not prior<frame['source_block_sequence']<=summary['published_prefixes']:
                raise ValueError('frame evidence inconsistent')
            for key in ('peak_db','rms_per_component_counts','spectrum_power_sum_counts_squared','analysis_ms','draw_ms'):
                if type(metric[key]) not in (int,float) or not math.isfinite(metric[key]):raise ValueError('invalid metric')
            prior=frame['source_block_sequence']
        if prior!=summary['last_display_sequence']:raise ValueError('last prefix differs')
        r.update(native_summary=summary,frame_metrics=metrics,source_frames=frames)
        r['after']=idle(actual);board.command('x='+work)
        raw=work+'/data/last-display-packed.bin';r['raw_sha256']=digest(raw);r['raw_bytes']=32768
        board.command('r='+raw);board.command('z=$r.gz');board.command('test ! -e $z');board.command('gzip -1 -c $r >$z',timeout=15)
        r['remote']=raw+'.gz';r['compressed_sha256']=digest(r['remote'])
        values=re.findall(r'^__BYTES__(\d+)__END__\r?$',board.command('echo __BYTES__$(wc -c <$z)__END__'),re.M)
        if len(values)!=1:raise ValueError('compressed bytes ambiguous')
        r['compressed_bytes']=int(values[0]);r['independent_final_idle_verified']=True
        r['status']='passed_autonomous_once_boot_RX_LCD_and_independent_idle_readback'
    except Exception as exc:
        r.update(status='failed_or_state_unconfirmed',error=repr(exc))
        if board:
            try:r['passive_tail']=board.read(3)
            except Exception as tail:r['passive_tail_error']=repr(tail)
    finally:
        if board:board.close()
        r.update(serial_closed=True,pending_one_shot_wrapper=armed,ended_utc=datetime.now(timezone.utc).isoformat());save()
    print(out);print(r['status'])
    return 0 if r['status'].startswith('passed_') else 1


if __name__=='__main__':raise SystemExit(main())
