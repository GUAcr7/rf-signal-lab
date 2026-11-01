"""Archive and independently review a stopped fixed-entry demo, without reboot/TX."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'experiments')]
spec = importlib.util.spec_from_file_location('fixed_board_control', ROOT / 'host/board_control.py')
control = importlib.util.module_from_spec(spec); spec.loader.exec_module(control)
from rfsig.board_session import WORK, require_rx_control, require_tx_off, score_observations
from p26_retrieve_chunks import decode_payload
from p36_retrieve_file import chunk_command, unpack_verified, validate_sizes, CHUNK_BYTES
from p52_ram import board_ram_tmp


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--demo', required=True, type=Path)
    args = parser.parse_args()
    demo = json.loads(args.demo.read_text('utf-8'))
    if demo['status'] != 'passed_P59_fixed_entry_full_short_demo_RX_TX_stopped':
        raise ValueError('Complete stopped fixed demo required')
    reports = []
    for step in demo['steps']:
        path = ROOT / step['report']
        if not step['passed'] or sha(path) != step['report_sha256']:
            raise ValueError('Demo step changed or failed')
        reports.append(json.loads(path.read_text('utf-8')))
    with control.operation_lock():
        c = control.Controller('archive')
        c.record.update(demo=args.demo.resolve().relative_to(ROOT).as_posix(),
                        demo_sha256=sha(args.demo), chunks=[])
        print(c.out, flush=True)
        error = None
        try:
            c.status()
            current = c.record['boards']['RX']
            require_rx_control(current, running=False)
            require_tx_off(c.record['boards']['TX'])
            if current['boot_id'] != demo['final_RX']['boot_id']:
                raise ValueError('Receiver boot changed')
            if current['AI']['calibration_token'] != demo['final_RX']['AI']['calibration_token']:
                raise ValueError('Different stopped session')
            names = ('ai-history.jsonl', 'ai.json', 'progress.json', 'summary.json', 'fb.raw')
            with c.board('RX') as (b, identity):
                info = c.inspect('RX', b, identity)
                require_rx_control(info, running=False)
                if info['boot_id'] != current['boot_id']:
                    raise ValueError('Receiver boot changed before archive')
                c.record['RAM_tmp'] = board_ram_tmp(b)
                stage = '/tmp/p35-p59arc-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
                b.command('z=' + stage); b.command('test ! -e $z'); b.command('mkdir $z')
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
                        raise ValueError('Ambiguous archive byte count')
                    return int(rows[0])
                size, raw_size = count(stage + '/e.gz'), count(stage + '/e.tar')
                validate_sizes(size, raw_size)
                wanted, raw_wanted = c.digest(b, stage + '/e.gz'), c.digest(b, stage + '/e.tar')
                c.record['contract'] = dict(remote=stage + '/e.gz', bytes=size, sha256=wanted,
                                            raw_bytes=raw_size, raw_sha256=raw_wanted)
                c.save(); b.command('src=' + stage + '/e.gz')
                pieces = []
                for index, start in enumerate(range(0, size, CHUNK_BYTES)):
                    expected = min(CHUNK_BYTES, size - start)
                    text = b.command(chunk_command(index, 'sha256sum'), timeout=20)
                    digest = re.findall(r'^([0-9a-f]{64})\s+-\r?$', text, re.M)
                    if len(digest) != 1:
                        raise ValueError('Ambiguous chunk digest')
                    accepted = None
                    for attempt in range(1, 4):
                        try:
                            data = decode_payload(b.command(chunk_command(index, 'base64'), timeout=20), expected)
                            if hashlib.sha256(data).hexdigest() != digest[0]:
                                raise ValueError('Chunk SHA mismatch')
                            accepted = data
                            break
                        except ValueError as failure:
                            c.record.setdefault('read_transfer_retries', []).append(
                                dict(index=index, attempt=attempt, error=repr(failure)))
                    if accepted is None:
                        raise ValueError('Transfer retries exhausted')
                    path = c.out / ('chunk-' + str(index).zfill(3) + '.gzpart')
                    path.write_bytes(accepted); pieces.append(accepted)
                    c.record['chunks'].append(dict(index=index, bytes=expected, sha256=digest[0], verified=True))
                    c.save()
                    print('P59 archived chunk ' + str(index + 1), flush=True)
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
                c.record['after_RX'] = ending
            rows = [json.loads(s) for s in (extracted / 'ai-history.jsonl').read_text('utf-8').splitlines()]
            if not rows or any(a['boot_id'] != current['boot_id'] for a in rows):
                raise ValueError('History has wrong boot')
            if any(a['model_sha256'] != current['AI']['model_sha256'] for a in rows):
                raise ValueError('History model changed')
            if any(b['elapsed_s'] <= a['elapsed_s'] for a, b in zip(rows, rows[1:])):
                raise ValueError('History timeline not increasing')
            if rows[0]['state'] != 'CALIBRATION_REQUIRED' or rows[-1]['state'] != 'STOPPED' or rows[-1]['accepted_class'] != -1:
                raise ValueError('History missing initial/final states')
            if any(a['accepted_class'] != -1 for a in rows if a['state'] != 'CLASSIFIED'):
                raise ValueError('Nonclassification state exposed a class')
            scores = {}
            for report in reports:
                if report['action'] != 'send' or report['source_truth'] == 'tone':
                    continue
                observations = report['AI_observations']
                anchor = observations[0]['elapsed_s']
                # Reuse the same frozen interval, now against every saved UI update.
                selected = [a for a in rows if anchor + 2 <= a['elapsed_s'] <= anchor + report['TX_seconds'] - 3]
                wanted_class = {'bpsk': 0, 'qpsk': 1, 'qam16': 2}[report['source_truth']]
                classified = [a for a in selected if a['state'] == 'CLASSIFIED' and a['accepted_class'] >= 0]
                correct = [a for a in classified if a['accepted_class'] == wanted_class]
                coverage = len(classified) / len(selected) if selected else 0
                accuracy = len(correct) / len(classified) if classified else 0
                scores[report['source_truth']] = dict(updates=len(selected), classified=len(classified), correct=len(correct),
                                                    coverage=coverage, conditional_accuracy=accuracy)
                if not selected or coverage < .70 or accuracy < .90:
                    raise ValueError('Full-history deployment gate failed')
            if set(scores) != {'bpsk', 'qpsk', 'qam16'}:
                raise ValueError('Three known-signal intervals missing')
            summary = json.loads((extracted / 'summary.json').read_text('utf-8'))
            if not all(summary.get(k) for k in ('buffer_released', 'context_released', 'worker_joined', 'RF_after_matches')) or summary.get('cleanup_unconfirmed'):
                raise ValueError('Archived cleanup not proven')
            c.record.update(result='verified_full_history_byte_archive_and_short_deployment_review',
                archived_members_sha256={name: sha(extracted / name) for name in names},
                history_updates=len(rows), state_counts=dict(Counter(a['state'] for a in rows)),
                full_history_deployment_scores=scores,
                elapsed_software_s=summary['elapsed_software_s'],
                ten_minute_claimed=False, ADC_continuity_claimed=False,
                new_independent_accuracy_claimed=False, human_visual_confirmation=False,
                IQ_replay_performed=False)
        except Exception as caught:
            error = caught
        control.finish_record(c, error is None, error)
        return int(error is not None)


if __name__ == '__main__':
    raise SystemExit(main())
