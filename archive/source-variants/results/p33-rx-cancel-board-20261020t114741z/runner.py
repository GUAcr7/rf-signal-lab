"""Run one pinned, receive-only cancellation experiment on a fresh identified boot.

Does not change RF settings, overlay, FPGA, PWM, boot files, or transmitter.
Only one process owns COM8; all raw command evidence is retained.
"""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import time
from p32_session import BoardConsole, ROOT

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-boot',required=True)
    parser.add_argument('--build-report',type=Path,required=True)
    args=parser.parse_args()
    build=json.loads(args.build_report.read_text('utf-8'))
    if build['status']!='cross_compile_verified' or not all(build['target_checks'].values()):
        raise RuntimeError('reviewed successful target build required')
    binary=Path(build['binary'])
    if sha(binary)!=build['binary_sha256'] or sha(Path(build['source']))!=build['source_sha256']:
        raise RuntimeError('binary/source changed since build')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out=ROOT/'results'/('p33-rx-cancel-board-'+stamp)
    out.mkdir(exist_ok=False)
    report=dict(status='preflight',stages=[],build_report=str(args.build_report.resolve()),
        binary_sha256=sha(binary),expected_boot=args.expected_boot,
        RF_attribute_writes=False,TX_operations=False,firmware_writes=False,
        scan_buffer_operations=True,scope='factory RF PL/driver, finite cancel/recreate only')
    (out/'runner.py').write_bytes(Path(__file__).read_bytes())
    (out/'build-report.json').write_bytes(args.build_report.read_bytes())
    (out/'source.c').write_bytes(Path(build['source']).read_bytes())
    (out/'arm-rx-cancel').write_bytes(binary.read_bytes())
    def save():
        (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    save()
    board=None
    phy=adc=None
    def state():
        board.command('cd '+phy)
        attrs={a:board.value(a) for a in ['in_voltage_sampling_frequency',
            'in_voltage_rf_bandwidth','out_altvoltage0_RX_LO_frequency',
            'in_voltage0_gain_control_mode','in_voltage0_hardwaregain',
            'in_voltage0_rf_port_select']}
        board.command('cd '+adc)
        return dict(boot_id=board.value('/proc/sys/kernel/random/boot_id'),
            tainted=board.value('/proc/sys/kernel/tainted'),attributes=attrs,
            buffer_enable=board.value('buffer/enable'),
            scan_enable=[board.value(f'scan_elements/in_voltage{i}_en') for i in range(4)])
    try:
        board=BoardConsole('COM8',report,save)
        board.shell()
        # A prior interrupted transfer can leave echo disabled. Restore it
        # without the echo-dependent command framing, then drain the prompt.
        board.port.write(b'stty echo\r')
        report['stages'].append(dict(stage='restore_tty_echo',output=board.read(.5)))
        if 'Zynq-Tronlong' not in board.command('uname -a'):
            raise RuntimeError('not expected receiver board')
        if board.value('/proc/sys/kernel/random/boot_id')!=args.expected_boot:
            raise RuntimeError('boot changed; identify again before experiment')
        processes=board.command('ps -ef')
        if re.search(r'arm-tx-source|p27-rx|arm-rx-capture|iio_readdev|p33-cancel',processes):
            raise RuntimeError('existing experiment process observed')
        board.command('/etc/rcS.d/S99board --check-rf')
        board.command('p=/sys/bus/iio/devices')
        text=board.command('for d in $p/iio:device*; do echo $d; cat $d/name; done')
        names={name:path for path,name in re.findall(r'(/sys/bus/iio/devices/iio:device\d+)\r?\n([^\r\n]+)',text)}
        phy,adc=names['ad9361-phy'],names['cf-ad9361-lpc']
        report['before']=before=state()
        expected=['30720000','18000000','2450000000','manual','0.000000 dB','A_BALANCED']
        if list(before['attributes'].values())!=expected or before['tainted']!='0' or before['buffer_enable']!='0' or before['scan_enable']!=['0']*4:
            raise RuntimeError('unexpected active state/configuration')
        board.command('dmesg | tail -n 100')
        remote='/tmp/p33-cancel-'+stamp[9:15]
        report['remote']=remote
        board.command('test ! -e '+remote)
        # Upload through the same no-DTR/RTS-reset serial handle. No Ctrl-C is
        # sent to another application; preflight already proved the shell idle.
        # With echo off the shell prompt prefixes the token output on the
        # same line, so the normal line-anchored command parser is unsuitable.
        board.port.write(b'stty -echo\r')
        report['stages'].append(dict(stage='disable_tty_echo',output=board.read(.5)))
        decoder_started=False
        try:
            board.port.write(('echo __P33_DATA__; base64 -d > '+remote+'\r').encode('ascii'))
            decoder_started=True
            banner=board.read(5,r'^__P33_DATA__\r?$')
            report['stages'].append(dict(stage='upload_decoder_banner',output=banner))
            save()
            if not re.search(r'^__P33_DATA__\r?$',banner,re.M):
                raise RuntimeError('upload decoder banner absent')
            encoded=base64.b64encode(binary.read_bytes())
            lines=[encoded[n:n+76] for n in range(0,len(encoded),76)]
            started=time.monotonic()
            sent=0
            for index in range(0,len(lines),16):
                block=b'\n'.join(lines[index:index+16])+b'\n'
                board.port.write(block)
                sent+=len(block)
                if board.port.in_waiting:
                    board.port.read(board.port.in_waiting)
                delay=sent/9000-(time.monotonic()-started)
                if delay>0:
                    time.sleep(delay)
            board.port.write(b'\n\x04')
            tail=board.read(8,r'(?:^|\n)[^\r\n]*#\s*$')
            report['stages'].append(dict(stage='upload_decoder_tail',output=tail))
            if not re.search(r'(?:^|\n)[^\r\n]*#\s*$',tail):
                raise RuntimeError('decoder did not return to shell')
            decoder_started=False
        finally:
            if decoder_started:
                # Only interrupt this runner's own incomplete decoder.
                board.port.write(b'\x03\r')
                board.read(1)
            board.port.write(b'stty echo\r')
            report['stages'].append(dict(stage='restore_tty_echo',output=board.read(.5)))
        digest=board.command('sha256sum '+remote)
        if not re.search(r'^'+build['binary_sha256']+r'\s',digest,re.M):
            raise RuntimeError('uploaded binary hash mismatch')
        board.command('chmod 755 '+remote)
        report['status']='running_receive_only'
        save()
        output=board.command(remote,timeout=90)
        (out/'program.txt').write_text(output,encoding='utf-8')
        rows=[json.loads(line.rstrip('\r')) for line in output.splitlines() if line.startswith('{')]
        (out/'program.json').write_text(json.dumps(rows,indent=2)+'\n',encoding='utf-8')
        cycles=[r for r in rows if r.get('schema')=='rfsig.rx_cancel_cycle.v1']
        completion=[r for r in rows if r.get('schema')=='rfsig.rx_cancel_completion.v1']
        if len(cycles)!=8 or [r['cycle'] for r in cycles]!=list(range(1,9)):
            raise RuntimeError('missing/duplicate cycle evidence')
        for row in cycles:
            if not (row['status']=='pass' and row['ready'] and row['active_observed_at_request']
                    and row['worker_terminal_result']<0 and row['negative_observed_after_request']
                    and row['canceled_buffer_refill_result']<0 and row['canceled_buffer_refill_elapsed_s']<=.25
                    and row['recovery_refills']==2 and row['rf_unchanged'] and not row['layout_error']):
                raise RuntimeError('failed cancellation/recovery evidence')
        if len(completion)!=1 or completion[0]['status']!='pass' or completion[0]['completed_cycles']!=8 or completion[0]['cleanup_unconfirmed']:
            raise RuntimeError('completion did not establish normal cleanup')
        report['program']=dict(cycles=cycles,completion=completion[0])
        report['status']='program_pass_pending_independent_state'
    except Exception as exc:
        report.update(status='failed',error=repr(exc))
    finally:
        if board:
            try:
                # Independent shell reads, not the executable's cleanup claim.
                if phy and adc:
                    report['after']=after=state()
                    report['independent_state_matches']=after==report.get('before')
                report['after_processes']=board.command('ps -ef')
                report['after_dmesg']=board.command('dmesg | tail -n 100')
                board.command('/etc/rcS.d/S99board --check-rf')
                if report['status']=='program_pass_pending_independent_state':
                    if not report.get('independent_state_matches'):
                        raise RuntimeError('independent board state differs after experiment')
                    if re.search(r'arm-tx-source|p27-rx|arm-rx-capture|iio_readdev|p33-cancel',report['after_processes']):
                        raise RuntimeError('experiment process remains')
                    report['status']='passed_finite_cancel_recreate_and_independent_idle_readback'
            except Exception as exc:
                report.update(status='failed_or_cleanup_unconfirmed',postcheck_error=repr(exc))
            finally:
                board.close()
        report['serial_closed']=True
        report['ended_utc']=datetime.now(timezone.utc).isoformat()
        save()
        print(out,flush=True)
        print(report['status'],flush=True)
    return 0 if report['status'].startswith('passed_') else 1

if __name__=='__main__':
    raise SystemExit(main())
