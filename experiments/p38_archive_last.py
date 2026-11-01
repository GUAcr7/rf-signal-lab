"""Prepare gzip of the last saved periodic RX buffer, after independent idle."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from p32_session import ROOT, BoardConsole
from p36_display_readback import AuditPort


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--board-report', type=Path, required=True)
    args = p.parse_args()
    parent = json.loads(args.board_report.read_text('utf-8'))
    if (parent['status'] != 'passed_periodic_RX_and_LCD_draw_with_independent_idle_readback'
            or not parent['independent_final_idle_verified'] or parent.get('native_completion_unconfirmed') is not False):
        raise ValueError('accepted completed periodic trial required')
    ram = parent['RAM_directory']
    if not re.fullmatch(r'/tmp/p35-p38-\d{6}', ram): raise ValueError('unexpected RAM directory')
    last = parent['cycles'][-1]
    if last['cycle'] != parent['requested_cycles']-1: raise ValueError('missing final cycle')
    raw = ram+'/data/cycle-'+str(last['cycle']).zfill(3)+'/iq-packed.bin'
    out = ROOT/'results'/datetime.now(timezone.utc).strftime('p38-last-archive-%Y%m%dT%H%M%SZ')
    out.mkdir(exist_ok=False)
    report = dict(status='preflight', stages=[], expected_boot=parent['expected_boot'],
                  parent_report=str(args.board_report.resolve()),
                  parent_report_sha256=hashlib.sha256(args.board_report.read_bytes()).hexdigest(),
                  raw_sha256=last['raw_sha256'], raw_bytes=262144, remote=raw+'.gz',
                  RF_operations=False, PL_operations=False)
    def save():
        (out/'report.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    board = None
    def digest(path):
        board.command('f='+path)
        values = re.findall(r'^([0-9a-f]{64})\s+\S+\r?$', board.command('sha256sum $f'), re.M)
        if len(values) != 1: raise RuntimeError('ambiguous SHA')
        return values[0]
    def idle():
        if board.value('/proc/sys/kernel/random/boot_id') != parent['expected_boot'] or board.value('/proc/sys/kernel/tainted') != '0':
            raise RuntimeError('identity changed')
        board.command('/etc/rcS.d/S99board --check-rf')
        if re.search(r'arm[-_]rx|arm[-_]panel|iio_readdev|p35-p38-[0-9]+/a', board.command('ps -ef')): raise RuntimeError('active experiment')
        board.command('p=/sys/bus/iio/devices')
        names = board.command('for d in $p/iio:device*; do echo $d; cat $d/name; done')
        matches = re.findall(r'(/sys/bus/iio/devices/iio:device\d+)\r?\ncf-ad9361-lpc\r?$', names, re.M)
        if len(matches) != 1: raise RuntimeError('ambiguous ADC')
        board.command('cd '+matches[0])
        if board.value('buffer/enable') != '0' or any(board.value('scan_elements/in_voltage'+str(i)+'_en') != '0' for i in range(4)):
            raise RuntimeError('RX not idle')
    save()
    try:
        board = BoardConsole('COM8', report, save); board.port = AuditPort(board.port, out); board.shell()
        idle()
        if digest(raw) != last['raw_sha256']: raise RuntimeError('raw source changed')
        board.command('r='+raw); board.command('z=$r.gz'); board.command('test ! -e $z')
        board.command('gzip -c $r >$z', timeout=15); board.command('gzip -t $z', timeout=10)
        report['compressed_sha256'] = digest(raw+'.gz')
        values = re.findall(r'^__BYTES__(\d+)__END__\r?$', board.command('echo __BYTES__$(wc -c <$z)__END__'), re.M)
        if len(values) != 1: raise RuntimeError('ambiguous size')
        report['compressed_bytes'] = int(values[0])
        if digest(raw) != last['raw_sha256']: raise RuntimeError('raw changed during compression')
        idle()
        report['status'] = 'gzip_verified_after_RX_idle_pending_host_archive'
    except Exception as error:
        report.update(status='failed', error=repr(error))
    finally:
        if board: board.close()
        report['serial_closed'] = True; save(); print(out); print(report['status'])
    return 0 if report['status'].startswith('gzip_verified') else 1


if __name__ == '__main__':
    raise SystemExit(main())
