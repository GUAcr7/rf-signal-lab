"""Bounded-host test of P42 long-running RX/LCD and atomic RAM progress."""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import time
from p32_session import ROOT, BoardConsole
from p35_once_merged_trial import AuditPort
from p35_uart_files import upload
from p36_full_rx_run import RF_EXPECTED, RF_NAMES, CRITICAL_KERNEL
from p38_run_rx_panel import detached_framebuffer_console
from p39_run_latest_panel import validate_summary


def sha(data): return hashlib.sha256(data).hexdigest()


def legacy_summary_reference(s, duration, interval, cancelled=False):
    required = dict(schema='rfsig.latest_panel.v1', status='stopped' if cancelled else 'pass',
        reason='signal_requested_stop' if cancelled else 'duration_complete',
        duration_ms_requested=duration, UI_interval_ms_requested=interval,
        worker_started=True, worker_joined=True, buffer_created=True, buffer_released=True,
        context_released=True, cleanup_unconfirmed=False, RF_before_valid=True, RF_after_matches=True,
        RF_attributes_written=False, TX_API_loaded=False, lossless_proven=False,
        ADC_gaps='unknown', analyse_only=False, prefix_frames=8192, frames_per_refill=65536,
        source_format='le:S12/16>>0', refill_error=0)
    for key, value in required.items():
        if type(s.get(key)) is not type(value) or s[key]!=value: raise ValueError('summary mismatch '+key)
    for key in ('published_prefixes','consumed_prefixes','last_display_sequence','UI_overwritten_prefixes','pending_prefixes_at_stop','display_updates','retained_prefix_bytes'):
        if type(s.get(key)) is not int or s[key]<0: raise ValueError('invalid counter '+key)
    if (s['pending_prefixes_at_stop'] not in (0,1)
        or s['consumed_prefixes']!=s['display_updates']
        or s['published_prefixes']!=s['consumed_prefixes']+s['UI_overwritten_prefixes']+s['pending_prefixes_at_stop']
        or not s['consumed_prefixes'] <= s['last_display_sequence'] <= s['published_prefixes']
        or s['retained_prefix_bytes']!=(32768 if s['display_updates'] else 0)):
        raise ValueError('mailbox accounting failed')
    if not cancelled and not s['display_updates']: raise ValueError('no displayed sample')
    elapsed = s.get('elapsed_software_s')
    if type(elapsed) not in (int,float) or not math.isfinite(elapsed) or elapsed<=0:
        raise ValueError('invalid elapsed time')
    if not cancelled and elapsed < duration/1000: raise ValueError('duration was not completed')
    return s


def validate_progress(s, duration, previous=None):
    if (s.get('schema')!='rfsig.live_progress.v1' or s.get('duration_ms_requested')!=duration
        or s.get('state') not in ('running','finished','stopped')
        or s.get('ADC_gaps')!='unknown' or s.get('lossless_proven') is not False):
        raise ValueError('progress identity/state differs')
    for key in ('display_updates','published_prefixes','consumed_prefixes','last_display_sequence',
                'UI_overwritten_prefixes','pending_prefixes','maxrss_kib'):
        if type(s.get(key)) is not int or s[key]<0:raise ValueError('invalid progress counter '+key)
    if (s['pending_prefixes'] not in (0,1) or s['consumed_prefixes']!=s['display_updates']
        or s['published_prefixes']!=s['consumed_prefixes']+s['UI_overwritten_prefixes']+s['pending_prefixes']
        or not s['consumed_prefixes']<=s['last_display_sequence']<=s['published_prefixes']
        or s['maxrss_kib']<=0):raise ValueError('progress accounting differs')
    for key in ('elapsed_software_s','peak_db','rms_per_component_counts'):
        if type(s.get(key)) not in (int,float) or not math.isfinite(s[key]):raise ValueError('invalid progress metric')
    if s['elapsed_software_s']<0:raise ValueError('negative progress elapsed')
    if previous:
        for key in ('display_updates','published_prefixes','consumed_prefixes','last_display_sequence','UI_overwritten_prefixes','elapsed_software_s','maxrss_kib'):
            if s[key]<previous[key]:raise ValueError('progress went backwards '+key)
    return s


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--expected-boot', required=True)
    p.add_argument('--build-report', type=Path, required=True)
    p.add_argument('--clock-acceptance', type=Path, required=True)
    p.add_argument('--duration-ms', type=int, default=3000)
    p.add_argument('--interval-ms', type=int, choices=range(250,1001), default=500)
    p.add_argument('--cancel-after-ms', type=int, default=0)
    args = p.parse_args()
    if args.duration_ms!=0 and not 1000<=args.duration_ms<=86400000:p.error('duration must be 0 or 1s..24h')
    if args.duration_ms==0 and not 1000<=args.cancel_after_ms<=86400000:p.error('until-signal board tests require a bounded host cancellation')
    if args.duration_ms and args.cancel_after_ms and not 1000<=args.cancel_after_ms<args.duration_ms-1000:
        p.error('cancel time must be >=1s and leave >=1s before the duration limit')
    build = json.loads(args.build_report.read_text('utf-8'))
    clock = json.loads(args.clock_acceptance.read_text('utf-8'))
    if (build.get('schema')!='rfsig.p42_build.v1' or build['status']!='passed_native_mock_tests_and_ARM_build_not_board_test'
        or build['test_count']<21 or not all(build['target_checks'].values())): raise ValueError('unaccepted build')
    for path,digest in build['inputs_sha256'].items():
        if sha((ROOT/path).read_bytes())!=digest: raise ValueError('build input changed '+path)
    binary = Path(build['binary']).read_bytes()
    if sha(binary)!=build['binary_sha256'] or len(binary)!=build['binary_bytes']: raise ValueError('binary changed')
    if clock['status']!='passed_ARM32_clock_overflow_fix_driver_register_consistency_this_boot' or clock['boot_id']!=args.expected_boot:
        raise ValueError('same-boot accepted safe clock required')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out=ROOT/'results'/('p42-board-'+stamp);out.mkdir(exist_ok=False)
    ram='/run/p42-'+stamp[9:15];stage='/tmp/p35-p42-'+stamp[9:15]
    r=dict(schema='rfsig.p42_board.v1',status='preflight',stages=[],expected_boot=args.expected_boot,
        build_report=str(args.build_report.resolve()),build_report_sha256=sha(args.build_report.read_bytes()),
        binary_sha256=sha(binary),clock_acceptance=str(args.clock_acceptance.resolve()),
        clock_acceptance_sha256=sha(args.clock_acceptance.read_bytes()),RAM_directory=ram,
        duration_ms=args.duration_ms,interval_ms=args.interval_ms,cancel_after_ms=args.cancel_after_ms,
        RF_attributes_written=False,TX_operations=False,PL_or_overlay_changes=False,startup_files_written=False,
        lossless_proven=False,physical_LCD_animation_confirmed=False,progress_samples=[])
    (out/'executed.py').write_bytes(Path(__file__).read_bytes())
    (out/'build-report.json').write_bytes(args.build_report.read_bytes())
    def save(): (out/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    board=None; native_may_run=False
    def digest(path):
        board.command('f='+path)
        values=re.findall(r'^([0-9a-f]{64})\s+\S+\r?$',board.command('sha256sum $f'),re.M)
        if len(values)!=1: raise RuntimeError('ambiguous SHA')
        return values[0]
    def inspect(label):
        state=dict(boot=board.value('/proc/sys/kernel/random/boot_id'),taint=board.value('/proc/sys/kernel/tainted'))
        if state!=dict(boot=args.expected_boot,taint='0'):raise RuntimeError('boot/taint changed')
        if 'Zynq-Tronlong' not in board.command('uname -a'):raise RuntimeError('wrong board')
        if digest('/etc/rcS.d/S99board')!=sha((ROOT/'board/boot/S99board').read_bytes()):raise RuntimeError('guard changed')
        if re.search(r'arm[-_]rx|arm[-_]panel|arm-latest|arm-tx-source|iio_readdev|p35-p3[89]-\d+/a|/run/p42-\d+/monitor',board.command('ps -ef')):
            raise RuntimeError('competing experiment')
        board.command('/etc/rcS.d/S99board --check-rf')
        board.command('ir=/sys/bus/iio/devices')
        text=board.command('for d in $ir/iio:device*;do echo $d;cat $d/name;done')
        pairs=re.findall(r'(/sys/bus/iio/devices/iio:device\d+)\r?\n([^\r\n]+)',text)
        if any(sum(n==name for _,n in pairs)!=1 for name in RF_NAMES):raise RuntimeError('missing/duplicate RF device')
        names={n:path for path,n in pairs};board.command('cd '+names['ad9361-phy'])
        state['attributes']={key:board.value(key) for key in RF_EXPECTED}
        if state['attributes']!=RF_EXPECTED:raise RuntimeError('RF settings differ')
        board.command('cd '+names['cf-ad9361-lpc'])
        state['buffer']=board.value('buffer/enable')
        state['scans']=[board.value('scan_elements/in_voltage'+str(i)+'_en') for i in range(4)]
        if state['buffer']!='0' or state['scans']!=['0']*4:raise RuntimeError('RX not idle')
        board.command('test -e /dev/fb0');board.command('v=/sys/class/vtconsole')
        text=board.command('for q in $v/vtcon*;do echo $q;cat $q/name $q/bind;done')
        if not detached_framebuffer_console(text):raise RuntimeError('fb console must already be detached')
        if re.search(CRITICAL_KERNEL,board.command('dmesg | tail -n 160')):raise RuntimeError('kernel error')
        r[label]=state;save();return state
    save()
    try:
        board=BoardConsole('COM8',r,save);board.port=AuditPort(board.port,out);board.shell()
        before=inspect('before');board.command('timeout -k 1 1 true')
        if not re.search(r'^\S+ /run tmpfs \S+',board.command('cat /proc/mounts'),re.M):raise RuntimeError('/run is not verified RAM tmpfs')
        r['RAM_filesystem_verified']=True;save()
        board.command('mkdir '+stage);upload(board,stage+'/a',binary)
        if digest(stage+'/a')!=sha(binary):raise RuntimeError('uploaded binary mismatch')
        board.command('mkdir '+ram);board.command('x='+ram);board.command('s='+stage)
        board.command('cp $s/a $x/monitor');board.command('chmod 755 $x/monitor')
        if digest(ram+'/monitor')!=sha(binary):raise RuntimeError('RAM binary mismatch')
        limit=math.ceil((args.duration_ms or args.cancel_after_ms)/1000)+10
        launch=('#!/bin/sh\nd='+ram+'\n'
            'timeout -k 22 '+str(limit)+' "$d/monitor" "$d/data" '+str(args.duration_ms)+' '+str(args.interval_ms)+' >"$d/log" 2>&1 &\n'
            'p=$!\necho "$p" >"$d/pid"\nwait "$p"\nr=$?\nprintf "%s\\n" "$r" >"$d/exit"\n').encode('ascii')
        upload(board,stage+'/run',launch);board.command('cp $s/run $x/run')
        board.command('sh $x/run >/dev/null 2>&1 &')
        native_may_run=True;r['status']='native_running';save()
        print('P42 RAM-backed receiver running '+ram,flush=True)
        start=time.monotonic();deadline=start+limit+30;cancelled=False;next_progress=start
        def progress():
            board.command('g=$x/data/progress.json')
            text=board.command('if test -f $g;then cat $g;fi')
            rows=[line for line in text.splitlines() if line.startswith('{')]
            if not rows:return None
            if len(rows)!=1 or len(rows[0].encode())>4096:raise RuntimeError('progress framing/size differs')
            value=validate_progress(json.loads(rows[0]),args.duration_ms,r['progress_samples'][-1] if r['progress_samples'] else None)
            r['progress_samples'].append(value);save();return value
        while True:
            if time.monotonic()>deadline:raise RuntimeError('native completion unconfirmed')
            reply=board.command('if test -f $x/exit;then cat $x/exit;else echo WAIT;fi')
            values=re.findall(r'^(WAIT|\d+)\r?$',reply,re.M)
            if len(values)!=1:raise RuntimeError('ambiguous exit status')
            if values[0]!='WAIT':
                native_may_run=False;r['launcher_exit_code']=int(values[0]);save()
                if int(values[0]) not in ((0,143) if cancelled else (0,)):raise RuntimeError('native nonzero exit')
                break
            if args.cancel_after_ms and not cancelled and (time.monotonic()-start)*1000>=args.cancel_after_ms:
                pid=board.value('$x/pid')
                if not re.fullmatch(r'[1-9]\d*',pid):raise RuntimeError('invalid owned timeout PID')
                board.command('p='+pid)
                text=board.command("echo __CMD__;base64 /proc/$p/cmdline;echo __END__")
                frame=re.search(r'(?m)^__CMD__\r?\n([A-Za-z0-9+/=\r\n]+)^__END__\r?$',text)
                if not frame:raise RuntimeError('owned timeout command not readable')
                argv=base64.b64decode(frame[1]).split(b'\0')
                if argv[0]!=b'timeout' or (ram+'/monitor').encode() not in argv:raise RuntimeError('PID no longer belongs to this native session')
                r['cancel_signal_intent_PID']=int(pid);save()
                board.command('kill -TERM $p');cancelled=True
            if time.monotonic()>=next_progress:
                current=progress();next_progress=time.monotonic()+10
                if current:print('Progress '+str(current['display_updates'])+' updates; '+str(current['maxrss_kib'])+' KiB max RSS',flush=True)
            time.sleep(.5 if args.cancel_after_ms else 2)
        sizes=re.findall(r'^__BYTES__(\d+)__END__\r?$',board.command('echo __BYTES__$(wc -c <$x/log)__END__'),re.M)
        if len(sizes)!=1 or not 0<int(sizes[0])<=4096:raise RuntimeError('native log exceeded fixed bound')
        r.update(native_log_bytes=int(sizes[0]),bounded_native_log_verified=True)
        log=board.command('cat $x/log',timeout=10);(out/'program.txt').write_text(log,encoding='utf-8')
        rows=[json.loads(line) for line in log.splitlines() if line.startswith('{')]
        summary=[json.loads(line) for line in board.command('cat $x/data/summary.json').splitlines() if line.startswith('{')]
        if len(summary)!=1:raise RuntimeError('missing summary')
        s=validate_summary(summary[0],args.duration_ms,args.interval_ms,cancelled)
        if (s.get('program_version')!='p42' or s.get('telemetry_mode')!='latest_atomic_progress_and_last_frame_only'
            or type(s.get('progress_commits')) is not int or s['progress_commits']!=s['display_updates']+1):raise RuntimeError('P42 summary differs')
        metrics=[v for v in rows if v.get('schema')=='rfsig.arm_panel_metrics.v2']
        frames=[v for v in rows if v.get('schema')=='rfsig.latest_frame.v1']
        if not len(metrics)==len(frames)==1 or len(rows)!=2:raise RuntimeError('expected only final frame/metrics')
        previous=0
        for i,(m,f) in enumerate(zip(metrics,frames)):
            if (m['iteration']!=s['display_updates']-1 or m['analyse_only'] or m['draw_ms']<=0 or m['frames']!=8
                or f['update']!=s['display_updates']-1 or not previous<f['source_block_sequence']<=s['published_prefixes']):raise RuntimeError('frame evidence differs')
            for key in ('peak_db','rms_per_component_counts','spectrum_power_sum_counts_squared','analysis_ms','draw_ms'):
                if type(m[key]) not in (int,float) or not math.isfinite(m[key]):raise RuntimeError('nonfinite metric')
            previous=f['source_block_sequence']
        if frames and previous!=s['last_display_sequence']:raise RuntimeError('saved/displayed sequence mismatch')
        r.update(native_summary=s,frame_metrics=metrics,source_frames=frames,cancel_signal_sent=cancelled)
        final=progress()
        if not final or final['state']!=('stopped' if cancelled else 'finished'):raise RuntimeError('missing final progress')
        for key in ('display_updates','published_prefixes','consumed_prefixes','last_display_sequence','UI_overwritten_prefixes'):
            if final[key]!=s[key]:raise RuntimeError('final progress/summary differs '+key)
        if final['pending_prefixes']!=s['pending_prefixes_at_stop']:raise RuntimeError('final pending differs')
        r['native_progress_final_verified']=True
        after=inspect('after')
        if after!=before:raise RuntimeError('independent post-state differs')
        board.command('x='+ram)
        if s['display_updates']:
            raw=ram+'/data/last-display-packed.bin';r['raw_sha256']=digest(raw);r['raw_bytes']=32768
            board.command('r='+raw);board.command('z=$r.gz');board.command('test ! -e $z')
            board.command('gzip -1 -c $r >$z',timeout=15)
            r['remote']=raw+'.gz';r['compressed_sha256']=digest(r['remote'])
            values=re.findall(r'^__BYTES__(\d+)__END__\r?$',board.command('echo __BYTES__$(wc -c <$z)__END__'),re.M)
            if len(values)!=1:raise RuntimeError('archive size ambiguous')
            r['compressed_bytes']=int(values[0])
        r['independent_final_idle_verified']=True
        r['status']='passed_long_running_RX_LCD_progress_and_independent_idle'
    except Exception as error:
        r.update(status='failed',error=repr(error))
        if board and not native_may_run:
            try:r['failure_postcheck']=inspect('failure_final_state')
            except Exception as tail:r['failure_postcheck_error']=repr(tail)
    finally:
        if board:board.close()
        r.update(serial_closed=True,native_completion_unconfirmed=native_may_run,ended_utc=datetime.now(timezone.utc).isoformat())
        save();print(out);print(r['status'])
    return 0 if r['status'].startswith('passed_') else 1


if __name__=='__main__':raise SystemExit(main())
