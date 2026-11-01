"""Install the tested guard atomically; never start/reload/reconfigure hardware."""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

from p26_retrieve_chunks import ChunkConsole, ROOT


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--boot-id', required=True)
    parser.add_argument('--checks', required=True, type=Path)
    args = parser.parse_args()
    checks = json.loads(args.checks.read_text('utf-8'))
    source = ROOT / 'board/boot/S99board'
    payload = source.read_bytes()
    new_hash = digest(payload)
    if checks['status'] != 'focused_checks_passed' or checks['script_sha256'] != new_hash:
        raise RuntimeError('exact new script has not passed focused checks')
    original = ROOT / 'results/p31-rf-driver-test-20261019T141834Z/S99board-before-guard.txt'
    old_hash = digest(original.read_bytes())
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out = ROOT / 'results' / ('p31-boot-guard-deploy-' + stamp)
    out.mkdir(exist_ok=False)
    (out / 'S99board.before').write_bytes(original.read_bytes())
    (out / 'S99board.after').write_bytes(payload)
    report = dict(status='preflight', stages=[], expected_boot_id=args.boot_id,
        checks=str(args.checks.resolve()), old_sha256=old_hash, new_sha256=new_hash,
        backup='/etc/p31-S99board-before-' + stamp,
        firmware_modified=False, overlays_modified=False, boot_script_executed=False,
        future_boot_behavior_hardware_tested=False)

    def save():
        (out / 'report.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')

    def check_hash(board, command, expected):
        result = board.command(command)
        actual = re.search(r'^([0-9a-f]{64})\s', result, re.M)
        if not actual or actual[1] != expected:
            raise RuntimeError('hash mismatch: ' + command)

    board = None
    save()
    try:
        board = ChunkConsole('COM8', report, save)
        if 'Zynq-Tronlong' not in board.command('uname -a'):
            raise RuntimeError('unexpected board')
        if args.boot_id not in board.command('cat /proc/sys/kernel/random/boot_id'):
            raise RuntimeError('unexpected boot session')
        board.command('/etc/rcS.d/S99board --check-rf')
        board.command('t=/etc/rcS.d/S99board')
        check_hash(board, 'sha256sum $t', old_hash)
        board.command('b=' + report['backup'])
        board.command('test ! -e $b')
        directory = '/tmp/p31-boot-' + stamp[9:15]
        board.command('mkdir ' + directory)
        board.command('s=' + directory + '/script.b64')
        for start in range(0, len(payload), 36):
            encoded = base64.b64encode(payload[start:start+36]).decode('ascii')
            board.command('echo ' + encoded + ' >> $s')
        board.command('n=' + directory + '/S99board')
        board.command('base64 -d $s > $n')
        check_hash(board, 'sha256sum $n', new_hash)
        board.command('sh -n $n')
        board.command('cp -p $t $b')
        check_hash(board, 'sha256sum $b', old_hash)
        report['status'] = 'original_backup_verified'
        save()
        board.command('u=/etc/rcS.d/.S99board.p31-new')
        board.command('test ! -e $u')
        board.command('cp $n $u')
        board.command('chmod 755 $u')
        check_hash(board, 'sha256sum $u', new_hash)
        board.command('mv $u $t')
        board.command('sync', timeout=20)
        check_hash(board, 'sha256sum $t', new_hash)
        board.command('test -x $t')
        board.command('/etc/rcS.d/S99board --check-rf')
        board.command('cat /proc/sys/kernel/tainted')
        report['status'] = 'guard_installed_backup_and_readback_verified_no_reload'
    except Exception as error:
        report.update(status='failed', error=repr(error))
    finally:
        if board:
            board.close()
        save()
        print(out)
        print(report['status'])
    return 1 if report['status'] == 'failed' else 0


if __name__ == '__main__':
    raise SystemExit(main())
