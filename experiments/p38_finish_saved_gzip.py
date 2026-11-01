"""Independently check an existing archive after a compression read timeout."""
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
    p.add_argument('--prepare-report', type=Path, required=True)
    args = p.parse_args()
    parent = json.loads(args.prepare_report.read_text('utf-8'))
    if (parent['schema'] != 'rfsig.p38_all_archive_prepare.v1'
            or parent['status'] != 'failed' or not parent.get('raw_sha256')
            or parent['stages'][-1]['command'] != 'gzip -c $r >$z'
            or parent['stages'][-1]['exit_code'] is not None):
        raise ValueError('expected a retained compression read timeout')
    remote = parent['remote']
    if not re.fullmatch(r'/tmp/p36-full-p38save-\d{6}/iq-packed\.bin\.gz', remote): raise ValueError('archive path')
    out = ROOT/'results'/datetime.now(timezone.utc).strftime('p38-all-archive-finish-%Y%m%dT%H%M%SZ')
    out.mkdir(exist_ok=False)
    report = {k: parent[k] for k in ('expected_boot', 'cycles', 'frames_per_cycle', 'bytes_per_cycle',
              'expected_cycle_sha256', 'board_source_paths', 'raw_bytes', 'remote', 'raw_sha256', 'parent_report')}
    report.update(status='preflight', stages=[], prepare_report=str(args.prepare_report.resolve()),
                  prepare_report_sha256=hashlib.sha256(args.prepare_report.read_bytes()).hexdigest(),
                  original_failed_report_modified=False, board_file_writes=False, RF_operations=False)
    (out/'executed.py').write_bytes(Path(__file__).read_bytes())
    def save(): (out/'report.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    board = None
    def digest(path):
        board.command('f='+path)
        values = re.findall(r'^([0-9a-f]{64})\s+\S+\r?$', board.command('sha256sum $f', timeout=20), re.M)
        if len(values) != 1: raise RuntimeError('ambiguous SHA')
        return values[0]
    save()
    try:
        board = BoardConsole('COM8', report, save); board.port = AuditPort(board.port, out)
        report['passive_tail'] = board.read(3); save()
        board.shell()
        if board.value('/proc/sys/kernel/random/boot_id') != parent['expected_boot'] or board.value('/proc/sys/kernel/tainted') != '0':
            raise RuntimeError('boot or kernel changed')
        if 'Zynq-Tronlong' not in board.command('uname -a'): raise RuntimeError('wrong board')
        if re.search(r'arm[-_]rx|arm[-_]panel|iio_readdev|\bgzip -c\b', board.command('ps -ef')): raise RuntimeError('archive or capture still running')
        board.command('/etc/rcS.d/S99board --check-rf')
        board.command('z='+remote)
        board.command('gzip -t $z', timeout=30)
        report['compressed_sha256'] = digest(remote)
        values = re.findall(r'^__BYTES__(\d+)__END__\r?$', board.command('echo __BYTES__$(wc -c <$z)__END__'), re.M)
        if len(values) != 1 or not 0 < int(values[0]) <= 8*1024*1024: raise RuntimeError('compressed size invalid')
        report['compressed_bytes'] = int(values[0])
        if digest(remote[:-3]) != parent['raw_sha256']: raise RuntimeError('raw archive changed')
        trial = json.loads(Path(parent['parent_report']).read_text('utf-8'))
        board.command('s='+trial['RAM_directory']+'/data')
        text = board.command('for f in $s/cycle-*/iq-packed.bin;do sha256sum $f;done', timeout=20)
        found = re.findall(r'^([0-9a-f]{64})\s+(/tmp/\S+)\r?$', text, re.M)
        if found != list(zip(parent['expected_cycle_sha256'], parent['board_source_paths'])):
            raise RuntimeError('original cycle sources changed')
        report['status'] = 'all_cycle_sources_verified_gzip_ready_pending_host_archive'
    except Exception as error:
        report.update(status='failed', error=repr(error))
    finally:
        if board: board.close()
        report['serial_closed'] = True; save(); print(out); print(report['status'])
    return 0 if report['status'].startswith('all_cycle_sources_') else 1


if __name__ == '__main__': raise SystemExit(main())
