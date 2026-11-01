"""Preserve all existing periodic RX buffers before poweroff; no new capture."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from p32_session import ROOT, BoardConsole
from p36_display_readback import AuditPort
from p36_full_rx_run import validate_metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--board-report', type=Path, required=True)
    args = parser.parse_args()
    parent = json.loads(args.board_report.read_text('utf-8'))
    count = parent['requested_cycles']
    if (parent['status'] != 'passed_periodic_RX_and_LCD_draw_with_independent_idle_readback'
            or parent.get('independent_final_idle_verified') is not True
            or parent.get('native_completion_unconfirmed', False)
            or type(count) is not int or not 1 <= count <= 64
            or len(parent['cycles']) != count):
        raise ValueError('accepted completed periodic trial required')
    ram = parent['RAM_directory']
    if not re.fullmatch(r'/tmp/p35-p38-\d{6}', ram): raise ValueError('unexpected RAM directory')
    expected = []
    for i, row in enumerate(parent['cycles']):
        if row['cycle'] != i or not re.fullmatch(r'[0-9a-f]{64}', row['raw_sha256']):
            raise ValueError('invalid cycle index/hash')
        validate_metadata(row['native_metadata'], 1)
        expected.append((row['raw_sha256'], ram+'/data/cycle-'+str(i).zfill(3)+'/iq-packed.bin'))
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out = ROOT/'results'/('p38-all-archive-prep-'+stamp); out.mkdir(exist_ok=False)
    destination = '/tmp/p36-full-p38save-'+stamp[9:15]
    raw = destination+'/iq-packed.bin'
    report = dict(schema='rfsig.p38_all_archive_prepare.v1', status='preflight', stages=[],
                  parent_report=str(args.board_report.resolve()),
                  parent_report_sha256=hashlib.sha256(args.board_report.read_bytes()).hexdigest(),
                  expected_boot=parent['expected_boot'], cycles=count,
                  frames_per_cycle=65536, bytes_per_cycle=262144,
                  expected_cycle_sha256=[digest for digest, _ in expected],
                  board_source_paths=[path for _, path in expected],
                  raw_bytes=count*262144, remote=raw+'.gz',
                  RF_operations=False, new_capture=False, PL_operations=False,
                  startup_files_written=False, original_files_modified=False)
    (out/'executed.py').write_bytes(Path(__file__).read_bytes())
    (out/'parent-report.json').write_bytes(args.board_report.read_bytes())
    def save(): (out/'report.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    board = None
    def idle():
        if board.value('/proc/sys/kernel/random/boot_id') != parent['expected_boot'] or board.value('/proc/sys/kernel/tainted') != '0':
            raise RuntimeError('boot or kernel state changed')
        if 'Zynq-Tronlong' not in board.command('uname -a'): raise RuntimeError('wrong board')
        if re.search(r'arm[-_]rx|arm[-_]panel|iio_readdev|p35-p38-[0-9]+/a', board.command('ps -ef')):
            raise RuntimeError('active RX experiment')
        board.command('/etc/rcS.d/S99board --check-rf')
        board.command('ir=/sys/bus/iio/devices')
        names = board.command('for d in $ir/iio:device*;do echo $d;cat $d/name;done')
        matches = re.findall(r'(/sys/bus/iio/devices/iio:device\d+)\r?\ncf-ad9361-lpc\r?$', names, re.M)
        if len(matches) != 1: raise RuntimeError('ambiguous ADC')
        board.command('cd '+matches[0])
        if board.value('buffer/enable') != '0' or any(board.value('scan_elements/in_voltage'+str(i)+'_en') != '0' for i in range(4)):
            raise RuntimeError('RX not idle')
    def sources():
        board.command('s='+ram+'/data')
        text = board.command('for f in $s/cycle-*/iq-packed.bin;do sha256sum $f;done', timeout=20)
        found = re.findall(r'^([0-9a-f]{64})\s+(/tmp/\S+)\r?$', text, re.M)
        if found != expected: raise RuntimeError('cycle files missing, additional, reordered or changed')
    def digest(path):
        board.command('f='+path)
        values = re.findall(r'^([0-9a-f]{64})\s+\S+\r?$', board.command('sha256sum $f', timeout=15), re.M)
        if len(values) != 1: raise RuntimeError('ambiguous digest')
        return values[0]
    def size(variable):
        text = board.command('echo __BYTES__$(wc -c <'+variable+')__END__')
        values = re.findall(r'^__BYTES__(\d+)__END__\r?$', text, re.M)
        if len(values) != 1: raise RuntimeError('ambiguous size')
        return int(values[0])
    save()
    try:
        board = BoardConsole('COM8', report, save); board.port = AuditPort(board.port, out); board.shell()
        idle()
        available = re.findall(r'^MemAvailable:\s+(\d+) kB\r?$', board.command('cat /proc/meminfo'), re.M)
        if len(available) != 1 or int(available[0])*1024 < report['raw_bytes']*2+32*1024*1024:
            raise RuntimeError('insufficient memory for archive')
        sources()
        board.command('mkdir '+destination); board.command('o='+destination)
        board.command('cat $s/cycle-*/iq-packed.bin >$o/iq-packed.bin', timeout=20)
        board.command('r=$o/iq-packed.bin')
        if size('$r') != report['raw_bytes']: raise RuntimeError('concatenated size mismatch')
        report['raw_sha256'] = digest(raw)
        board.command('z=$r.gz'); board.command('gzip -c $r >$z', timeout=30)
        board.command('gzip -t $z', timeout=30)
        report['compressed_sha256'] = digest(raw+'.gz'); report['compressed_bytes'] = size('$z')
        if not 0 < report['compressed_bytes'] <= 8*1024*1024: raise RuntimeError('compressed archive exceeds transfer contract')
        sources(); idle()
        report['status'] = 'all_cycle_sources_verified_gzip_ready_pending_host_archive'
    except Exception as error:
        report.update(status='failed', error=repr(error))
    finally:
        if board: board.close()
        report['serial_closed'] = True; save(); print(out); print(report['status'])
    return 0 if report['status'].startswith('all_cycle_sources_') else 1


if __name__ == '__main__':
    raise SystemExit(main())
