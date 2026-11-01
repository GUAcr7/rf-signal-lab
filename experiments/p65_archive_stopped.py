"""Save the stopped P65 RX session without RF or new acquisition claims."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile

from p59_archive_session import (
    ROOT, control, WORK, require_rx_control, require_tx_off, board_ram_tmp,
    validate_sizes, CHUNK_BYTES, chunk_command, decode_payload, unpack_verified,
)
from rfsig.board_session import rx_cleanup_confirmed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stopped-report', type=Path, required=True)
    args = parser.parse_args()
    bound = json.loads(args.stopped_report.read_text('utf-8'))
    if bound['status'] != 'passed_P59_stop' or not bound['serial_closed']:
        raise ValueError('A completed stop report is required')
    expected = bound['after_RX']
    require_rx_control(expected, running=False)
    names = ('ai-history.jsonl', 'ai.json', 'progress.json', 'summary.json', 'fb.raw')
    with control.operation_lock():
        c = control.Controller('p65-archive-stopped')
        c.record.update(stopped_report=args.stopped_report.resolve().relative_to(ROOT).as_posix(),
                        stopped_report_sha256=hashlib.sha256(args.stopped_report.read_bytes()).hexdigest(),
                        chunks=[], RF_transmissions=0, new_acquisition=False)
        print(c.out, flush=True)
        error = None
        try:
            c.status()
            current = c.record['boards']['RX']
            require_rx_control(current, running=False)
            require_tx_off(c.record['boards']['TX'])
            for key in ('boot_id', 'progress', 'AI', 'RF', 'profile_hashes'):
                if current.get(key) != expected.get(key):
                    raise ValueError('Stopped RX changed: ' + key)
            with c.board('RX') as (b, identity):
                initial = c.inspect('RX', b, identity)
                require_rx_control(initial, running=False)
                if initial['boot_id'] != expected['boot_id'] or initial['progress'] != expected['progress']:
                    raise ValueError('RX changed before archive')
                c.record['RAM_tmp'] = board_ram_tmp(b)
                stage = '/tmp/p35-p65arc-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
                b.command('z=' + stage)
                b.command('test ! -e $z'); b.command('mkdir $z')
                b.command('w=' + WORK)
                b.command("f='" + ' '.join(names) + "'")
                b.command('tar -cf $z/e.tar -C $w/data $f', timeout=20)
                b.command('gzip -1 -c $z/e.tar >$z/e.gz', timeout=20)
                b.command('gzip -t $z/e.gz')
                def count(path):
                    b.command('v=' + path)
                    text = b.command('echo __N__$(wc -c <$v)__E__')
                    rows = re.findall(r'^__N__(\d+)__E__\r?$', text, re.M)
                    if len(rows) != 1:
                        raise ValueError('Ambiguous archive size')
                    return int(rows[0])
                size, raw_size = count(stage + '/e.gz'), count(stage + '/e.tar')
                validate_sizes(size, raw_size)
                wanted, raw_wanted = c.digest(b, stage + '/e.gz'), c.digest(b, stage + '/e.tar')
                c.record['contract'] = dict(remote=stage + '/e.gz', bytes=size, sha256=wanted,
                                             raw_bytes=raw_size, raw_sha256=raw_wanted)
                c.save(); b.command('src=' + stage + '/e.gz')
                pieces = []
                for index, start in enumerate(range(0, size, CHUNK_BYTES)):
                    expected_size = min(CHUNK_BYTES, size - start)
                    text = b.command(chunk_command(index, 'sha256sum'), timeout=20)
                    digest = re.findall(r'^([0-9a-f]{64})\s+-\r?$', text, re.M)
                    if len(digest) != 1:
                        raise ValueError('Ambiguous chunk SHA')
                    data = decode_payload(b.command(chunk_command(index, 'base64'), timeout=20), expected_size)
                    if hashlib.sha256(data).hexdigest() != digest[0]:
                        raise ValueError('Chunk SHA mismatch')
                    pieces.append(data)
                    c.record['chunks'].append(dict(index=index, bytes=len(data), sha256=digest[0]))
                    c.save()
                packed = b''.join(pieces)
                raw = unpack_verified(packed, size, wanted, raw_size, raw_wanted)
                (c.out / 'evidence.tar.gz').write_bytes(packed)
                extracted = c.out / 'files'; extracted.mkdir()
                with tarfile.open(fileobj=io.BytesIO(raw), mode='r:') as archive:
                    members = archive.getmembers()
                    if len(members) != len(names) or {m.name for m in members} != set(names) or not all(m.isfile() for m in members):
                        raise ValueError('Unexpected archive members')
                    for member in members:
                        (extracted / member.name).write_bytes(archive.extractfile(member).read())
                if c.digest(b, stage + '/e.gz') != wanted:
                    raise ValueError('Archive changed during transfer')
                ending = c.inspect('RX', b, identity)
                require_rx_control(ending, running=False)
                for key in ('boot_id', 'progress', 'AI', 'RF', 'profile_hashes'):
                    if ending.get(key) != current.get(key):
                        raise ValueError('RX changed during archive: ' + key)
                c.record['after_RX'] = ending
            summary = json.loads((extracted / 'summary.json').read_text('utf-8'))
            if not rx_cleanup_confirmed(summary):
                raise ValueError('Archived cleanup incomplete')
            rows = [json.loads(line) for line in (extracted / 'ai-history.jsonl').read_text('utf-8').splitlines()]
            if not rows or any(row['boot_id'] != expected['boot_id'] for row in rows):
                raise ValueError('History boot mismatch')
            if any(row['model_sha256'] != expected['AI']['model_sha256'] for row in rows):
                raise ValueError('History model mismatch')
            if rows[0]['state'] != 'CALIBRATION_REQUIRED' or rows[-1]['state'] != 'STOPPED':
                raise ValueError('Unexpected history endpoints')
            if any(row['accepted_class'] != -1 for row in rows):
                raise ValueError('Uncalibrated session unexpectedly accepted a class')
            if any(b['elapsed_s'] <= a['elapsed_s'] for a, b in zip(rows, rows[1:])):
                raise ValueError('Nonincreasing history')
            c.record.update(result='verified_P65_stopped_session_byte_archive_only',
                archived_members_sha256={name: hashlib.sha256((extracted / name).read_bytes()).hexdigest() for name in names},
                history_updates=len(rows), state_counts=dict(Counter(row['state'] for row in rows)),
                RF_validation_claimed=False, AI_accuracy_claimed=False, human_visual_confirmation=False)
        except Exception as caught:
            error = caught
        control.finish_record(c, error is None, error)
        return int(error is not None)


if __name__ == '__main__':
    raise SystemExit(main())
