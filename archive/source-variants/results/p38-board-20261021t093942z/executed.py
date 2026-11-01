"""One bounded periodic native RX/LCD trial; no firmware, RF or startup writes."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from p32_session import ROOT, BoardConsole
from p35_once_merged_trial import AuditPort
from p35_uart_files import upload
from p36_full_rx_run import RF_EXPECTED, RF_NAMES, CRITICAL_KERNEL, validate_metadata


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-boot', required=True)
    parser.add_argument('--build-report', type=Path, required=True)
    parser.add_argument('--clock-acceptance', type=Path, required=True)
    parser.add_argument('--cycles', type=int, choices=range(1, 33), default=8)
    parser.add_argument('--interval-ms', type=int, choices=range(100, 501), default=250)
    args = parser.parse_args()
    build = json.loads(args.build_report.read_text('utf-8'))
    acceptance = json.loads(args.clock_acceptance.read_text('utf-8'))
    if (build['status'] != 'passed_mock_regressions_and_ARM_build_not_board_test'
            or build['test_count'] != 12 or not all(build['target_checks'].values())):
        raise ValueError('unaccepted native build')
    for name, digest in build['inputs_sha256'].items():
        if sha((ROOT/name).read_bytes()) != digest:
            raise ValueError('build input changed: '+name)
    binary = Path(build['binary']).read_bytes()
    if len(binary) != build['binary_bytes'] or sha(binary) != build['binary_sha256']:
        raise ValueError('binary changed')
    if (acceptance['status'] != 'passed_ARM32_clock_overflow_fix_driver_register_consistency_this_boot'
            or acceptance['boot_id'] != args.expected_boot):
        raise ValueError('accepted same-boot P37 clock evidence required')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out = ROOT/'results'/('p38-board-'+stamp)
    out.mkdir(exist_ok=False)
    ram = '/tmp/p38-'+stamp[9:15]
    report = dict(schema='rfsig.p38_board.v1', status='preflight', stages=[],
                  expected_boot=args.expected_boot, build_report=str(args.build_report.resolve()),
                  build_report_sha256=sha(args.build_report.read_bytes()),
                  binary_sha256=sha(binary), clock_acceptance=str(args.clock_acceptance.resolve()),
                  clock_acceptance_sha256=sha(args.clock_acceptance.read_bytes()),
                  requested_cycles=args.cycles, interval_ms=args.interval_ms, RAM_directory=ram,
                  RF_attribute_writes=False, TX_operations=False, PL_or_overlay_changes=False,
                  startup_files_written=False, continuous_RX=False, lossless_proven=False,
                  physical_LCD_updated_visibility_verified=False, stages_scope='periodic finite captures then draw')
    (out/'executed.py').write_bytes(Path(__file__).read_bytes())
    (out/'build-report.json').write_bytes(args.build_report.read_bytes())
    def save():
        (out/'report.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    board = None
    safe_shell = False
    def digest(path):
        board.command('f='+path)
        values = re.findall(r'^([0-9a-f]{64})\s+\S+\r?$', board.command('sha256sum $f'), re.M)
        if len(values) != 1: raise RuntimeError('ambiguous SHA')
        return values[0]
    def inspect(label):
        state = dict(boot=board.value('/proc/sys/kernel/random/boot_id'), taint=board.value('/proc/sys/kernel/tainted'))
        if state != dict(boot=args.expected_boot, taint='0'): raise RuntimeError('boot or taint changed')
        if 'Zynq-Tronlong' not in board.command('uname -a'): raise RuntimeError('wrong board')
        if digest('/etc/rcS.d/S99board') != sha((ROOT/'board/boot/S99board').read_bytes()): raise RuntimeError('guard changed')
        if board.value('/etc/board-mode') != 'rf': raise RuntimeError('unexpected mode')
        processes = board.command('ps -ef')
        if re.search(r'arm[-_]rx|arm[-_]panel|arm-tx-source|p27-rx|p33-cancel|iio_readdev|/tmp/p38-[0-9]+/a', processes):
            raise RuntimeError('competing experiment')
        board.command('/etc/rcS.d/S99board --check-rf')
        board.command('p=/sys/bus/iio/devices')
        text = board.command('for d in $p/iio:device*; do echo $d; cat $d/name; done')
        pairs = re.findall(r'(/sys/bus/iio/devices/iio:device\d+)\r?\n([^\r\n]+)', text)
        if any(sum(n == name for _, n in pairs) != 1 for name in RF_NAMES): raise RuntimeError('RF devices missing/duplicate')
        names = {n: p for p, n in pairs}
        board.command('cd '+names['ad9361-phy'])
        state['RF_attributes'] = {key: board.value(key) for key in RF_EXPECTED}
        if state['RF_attributes'] != RF_EXPECTED: raise RuntimeError('fixed RF configuration changed')
        board.command('cd '+names['cf-ad9361-lpc'])
        state['buffer'] = board.value('buffer/enable')
        state['scans'] = [board.value('scan_elements/in_voltage'+str(i)+'_en') for i in range(4)]
        if state['buffer'] != '0' or state['scans'] != ['0']*4: raise RuntimeError('RX not independently idle')
        board.command('test -e /dev/fb0')
        # Do not detach UART/fb consoles here. An existing detached fb console
        # is required so no console can overwrite the monitor pixels.
        board.command('v=/sys/class/vtconsole')
        consoles = board.command('for q in $v/vtcon*; do echo $q; cat $q/name $q/bind; done')
        if not re.search(r'frame buffer device\)\r?\n0\r?$', consoles, re.M):
            raise RuntimeError('detached framebuffer console not established')
        if re.search(CRITICAL_KERNEL, board.command('dmesg | tail -n 160')): raise RuntimeError('kernel error')
        report[label] = state; save()
        return state
    save()
    try:
        board = BoardConsole('COM8', report, save); board.port = AuditPort(board.port, out)
        board.shell(); safe_shell = True
        before = inspect('before')
        board.command('timeout -k 1 1 true')
        available = re.findall(r'^MemAvailable:\s+(\d+) kB\r?$', board.command('cat /proc/meminfo'), re.M)
        if len(available) != 1 or int(available[0])*1024 < args.cycles*262144+32*1024*1024: raise RuntimeError('insufficient memory')
        board.command('mkdir '+ram)
        upload(board, ram+'/a', binary)
        if digest(ram+'/a') != build['binary_sha256']: raise RuntimeError('uploaded binary SHA mismatch')
        board.command('x='+ram); board.command('chmod 755 $x/a')
        report['status'] = 'finite_monitor_intent'; save()
        command = 'timeout -k 22 30 $x/a $x/data '+str(args.cycles)+' '+str(args.interval_ms)+' >$x/log 2>&1'
        safe_shell = False
        try:
            board.command(command, timeout=58); safe_shell = True
        except Exception:
            if type(report['stages'][-1].get('exit_code')) is int: safe_shell = True
            raise
        log = board.command('cat $x/log', timeout=25)
        (out/'program.txt').write_text(log, encoding='utf-8')
        rows = [json.loads(line) for line in log.splitlines() if line.startswith('{')]
        starts = [r for r in rows if r.get('schema') == 'rfsig.full_rx_start.v1']
        ends = [r for r in rows if r.get('schema') == 'rfsig.full_rx_completion.v1']
        metrics = [r for r in rows if r.get('schema') == 'rfsig.arm_panel_metrics.v2']
        if not len(starts) == len(ends) == len(metrics) == args.cycles: raise RuntimeError('missing/duplicate cycle records')
        if len(rows) != 3*args.cycles: raise RuntimeError('unknown native records')
        for i, (start, end, metric) in enumerate(zip(starts, ends, metrics)):
            if (start['requested_blocks'] != 1 or end['status'] != 'pass' or end['completed_blocks'] != 1
                    or end['raw_file_bytes_written'] != 262144 or not end['rf_after_matches']
                    or not end['buffer_released'] or not end['context_released'] or end['cleanup_unconfirmed']
                    or metric['iteration'] != i or metric['analyse_only'] or metric['draw_ms'] <= 0):
                raise RuntimeError('cycle contract mismatch')
        summary_rows = [json.loads(line) for line in board.command('cat $x/data/summary.json').splitlines() if line.startswith('{')]
        if len(summary_rows) != 1: raise RuntimeError('ambiguous summary')
        summary = summary_rows[0]
        if summary['status'] != 'pass' or summary['completed_cycles'] != args.cycles or summary['continuous_RX'] or summary['lossless_proven']:
            raise RuntimeError('unaccepted summary')
        report.update(native_summary=summary, cycle_metrics=metrics)
        after = inspect('after')
        if after != before: raise RuntimeError('independent post-state differs')
        # inspect() uses shell variables a,d,p,q; x is deliberately distinct.
        board.command('x='+ram)
        evidence = []
        for i in range(args.cycles):
            prefix = ram+'/data/cycle-'+str(i).zfill(3)
            board.command('m='+prefix+'/metadata.json')
            mrows = [json.loads(line) for line in board.command('cat $m').splitlines() if line.startswith('{')]
            if len(mrows) != 1: raise RuntimeError('metadata frame count')
            validate_metadata(mrows[0], 1)
            raw_sha = digest(prefix+'/iq-packed.bin')
            evidence.append(dict(cycle=i, raw_sha256=raw_sha, native_metadata=mrows[0]))
        report['cycles'] = evidence
        report['status'] = 'passed_periodic_RX_and_LCD_draw_with_independent_idle_readback'
        report['independent_final_idle_verified'] = True
    except Exception as error:
        report.update(status='failed', error=repr(error), shell_return_confirmed=safe_shell)
        if board and safe_shell:
            try:
                if 'RAM_directory' in report:
                    board.command('x='+ram)
                    report['failure_log'] = board.command('test ! -f $x/log || cat $x/log', timeout=20)
                inspect('failure_final_state')
            except Exception as tail:
                report['failure_postcheck_error'] = repr(tail)
    finally:
        if board: board.close()
        report['serial_closed'] = True
        report['ended_utc'] = datetime.now(timezone.utc).isoformat(); save()
        print(out); print(report['status'])
    return 0 if report['status'].startswith('passed_') else 1


if __name__ == '__main__':
    raise SystemExit(main())
