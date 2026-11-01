"""Archive an existing compressed board file with bounded, SHA-checked chunks.

Only board file reads, identity/idle checks and shell variables are used. This
does not capture RF, change RX attributes, bind consoles, or create board files.
The archive proves the specified bytes arrived intact; it does not prove that
the acquisition was lossless, continuous, correctly laid out, or physically shown.
"""
import argparse
import binascii
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import time
import uuid

from p26_retrieve_chunks import decode_payload
from p32_session import BoardConsole, ROOT
from p35_once_merged_trial import AuditPort

CHUNK_BYTES = 32768
MAX_COMPRESSED_BYTES = 8 * 1024 * 1024
MAX_RAW_BYTES = 16 * 1024 * 1024
RF_NAMES = {'ad9361-phy', 'cf-ad9361-lpc', 'cf-ad9361-dds-core-lpc'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def remote_path(value):
    if not re.fullmatch(r'(?:/tmp/p35-[A-Za-z0-9_-]{1,32}/fb\.raw\.gz|'
                        r'/tmp/p36-full-[A-Za-z0-9_-]{1,32}/iq-packed\.bin\.gz|'
                        r'/tmp/p35-p38-\d{6}/data/cycle-0(?:[0-5]\d|6[0-3])/iq-packed\.bin\.gz|'
                        r'/tmp/p35-p39-\d{6}/data/last-display-packed\.bin\.gz|'
                        r'/run/p42-\d{6}/data/last-display-packed\.bin\.gz)', value):
        raise argparse.ArgumentTypeError('unexpected compressed evidence path')
    if len('src=' + value) > 72:
        raise argparse.ArgumentTypeError('remote assignment exceeds UART line limit')
    return value


def digest_argument(value):
    if not re.fullmatch(r'[0-9a-f]{64}', value):
        raise argparse.ArgumentTypeError('expected lowercase SHA256')
    return value


def boot_argument(value):
    if not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', value):
        raise argparse.ArgumentTypeError('expected lowercase UUID boot ID')
    return value


def byte_count(value):
    if not re.fullmatch(r'[1-9][0-9]*', value):
        raise argparse.ArgumentTypeError('expected a positive integer byte count')
    return int(value)


def validate_sizes(compressed_bytes, raw_bytes):
    if (type(compressed_bytes) is not int or not 1 <= compressed_bytes <= MAX_COMPRESSED_BYTES
            or type(raw_bytes) is not int or not 1 <= raw_bytes <= MAX_RAW_BYTES):
        raise ValueError('compressed/raw byte count exceeds 8/16 MiB bounds')


def chunk_command(index, encoding):
    if type(index) is not int or not 0 <= index < MAX_COMPRESSED_BYTES // CHUNK_BYTES:
        raise ValueError('invalid chunk index')
    if encoding not in ('sha256sum', 'base64'):
        raise ValueError('unexpected chunk operation')
    command = f'dd if=$src bs={CHUNK_BYTES} skip={index} count=1 2>/dev/null | {encoding}'
    if len(command) > 72:
        raise ValueError('chunk command exceeds UART line limit')
    return command


def unpack_verified(packed, expected_bytes, expected_sha, raw_bytes, raw_sha):
    """Bounded local gzip read also forces CRC/footer validation at EOF."""
    validate_sizes(expected_bytes, raw_bytes)
    if len(packed) != expected_bytes or sha(packed) != expected_sha:
        raise ValueError('complete compressed size/SHA mismatch')
    with gzip.GzipFile(fileobj=io.BytesIO(packed), mode='rb') as source:
        raw = source.read(raw_bytes + 1)
    if len(raw) != raw_bytes or sha(raw) != raw_sha:
        raise ValueError('complete raw size/SHA mismatch or decompression exceeded bound')
    return raw


class RetrievalConsole(BoardConsole):
    """DTR/RTS-off BoardConsole plus raw audit and compact payload stage logs."""
    def __init__(self, record, save, out):
        super().__init__('COM8', record, save)
        self.port = AuditPort(self.port, out)

    def read(self, seconds, pattern=None):
        if seconds > 12:
            raise ValueError('retrieval reads are bounded to 12 seconds')
        matcher = re.compile(pattern.encode('ascii'), re.M) if pattern else None
        data = bytearray()
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            data.extend(self.port.read(self.port.in_waiting or 1))
            if matcher and matcher.search(data[max(0, len(data) - 4096):]):
                break
        return data.decode('ascii', errors='replace')

    def command(self, command, timeout=8, payload=False):
        if len(command) > 72 or '\n' in command or '\r' in command or not 0 < timeout <= 12:
            raise ValueError('command must be one line <=72 characters, timeout <=12 seconds')
        token = '__P36_' + uuid.uuid4().hex[:8] + '__'
        self.port.write((command + '\recho ' + token + ':$?\r').encode('ascii'))
        text = self.read(timeout, r'^' + token + r':\d+\r?$')
        found = re.search(r'^' + token + r':(\d+)\r?$', text, re.M)
        rc = int(found[1]) if found else None
        stage = dict(port=self.name, command=command, exit_code=rc,
                     utc=datetime.now(timezone.utc).isoformat())
        if payload:
            stage.update(output_omitted='base64 bytes preserved in uart.rx.bin',
                         output_chars=len(text), decoded_transcript_sha256=sha(text.encode('utf-8')))
        else:
            stage['output'] = text
        self.record['stages'].append(stage)
        self.save()
        if rc != 0:
            # No transfer retry after a missing RC: the shell is unconfirmed.
            raise RuntimeError(f'{self.name} command failed rc={rc}: {command}')
        return text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-boot', type=boot_argument, required=True)
    parser.add_argument('--remote', type=remote_path, required=True)
    parser.add_argument('--expected-bytes', type=byte_count, required=True)
    parser.add_argument('--expected-sha256', type=digest_argument, required=True)
    parser.add_argument('--raw-bytes', type=byte_count, required=True)
    parser.add_argument('--raw-sha256', type=digest_argument, required=True)
    parser.add_argument('--resume-from', type=Path,
                        help='Reuse verified local prefix chunks into a NEW report; old evidence remains unchanged')
    args = parser.parse_args()
    validate_sizes(args.expected_bytes, args.raw_bytes)
    reused = {}
    if args.resume_from:
        previous_path = args.resume_from.resolve(strict=True)
        if not previous_path.is_relative_to((ROOT / 'results').resolve()) or previous_path.name != 'report.json':
            raise ValueError('resume source must be local results/report.json')
        previous = json.loads(previous_path.read_text('utf-8'))
        for key, value in dict(expected_boot=args.expected_boot, remote=args.remote,
                               expected_bytes=args.expected_bytes, expected_sha256=args.expected_sha256,
                               raw_bytes=args.raw_bytes, raw_sha256=args.raw_sha256).items():
            if previous.get(key) != value:
                raise ValueError('resume identity/byte contract differs: ' + key)
        for row in previous.get('chunks', []):
            if not row.get('verified'):
                break
            index = row.get('index')
            if type(index) is not int or index != len(reused):
                raise ValueError('resume chunks must be an ordered prefix')
            name = row.get('local_file', '')
            if name != 'chunk-' + str(index).zfill(3) + '.gzpart':
                raise ValueError('unexpected resume chunk basename')
            data = (previous_path.parent / name).read_bytes()
            wanted = min(CHUNK_BYTES, args.expected_bytes-index*CHUNK_BYTES)
            if len(data) != wanted or wanted <= 0 or sha(data) != row.get('sha256'):
                raise ValueError('resume local chunk changed')
            reused[index] = (data, row['sha256'])
    guard = (ROOT / 'board/boot/S99board').read_bytes()
    out = ROOT / 'results' / datetime.now(timezone.utc).strftime('p36-file-archive-%Y%m%dT%H%M%SZ')
    out.mkdir(exist_ok=False)
    record = dict(schema='rfsig.p36_file_archive.v1', status='preflight',
                  created_utc=datetime.now(timezone.utc).isoformat(), stages=[], checks=[], chunks=[],
                  expected_boot=args.expected_boot, remote=args.remote,
                  expected_bytes=args.expected_bytes, expected_sha256=args.expected_sha256,
                  raw_bytes=args.raw_bytes, raw_sha256=args.raw_sha256,
                  guard_sha256=sha(guard), chunk_bytes=CHUNK_BYTES,
                  max_attempts_per_chunk=3, command_timeout_seconds=12,
                  board_file_writes=False, RF_operations=False, PL_or_overlay_operations=False,
                  lossless_proven=False, continuous_ADC_timeline_verified=False,
                  IQ_layout_verified=False, physical_display_verified=False,
                  limitations=['Byte-exact archive only; acquisition and physical output need separate evidence'])
    if args.resume_from:
        record.update(resume_from=str(previous_path), resume_report_sha256=sha(previous_path.read_bytes()),
                      local_prefix_chunks_verified=len(reused), previous_report_modified=False)

    def save():
        (out / 'report.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')

    def check(name, condition):
        record['checks'].append(dict(name=name, passed=bool(condition)))
        save()
        if not condition:
            raise RuntimeError(name)

    def inspect(label):
        check(label + ' receiver identity', 'Zynq-Tronlong' in board.command('uname -a'))
        check(label + ' same boot', board.value('/proc/sys/kernel/random/boot_id') == args.expected_boot)
        check(label + ' untainted', board.value('/proc/sys/kernel/tainted') == '0')
        board.command('g=/etc/rcS.d/S99board')
        guards = re.findall(r'^([0-9a-f]{64})\s+\S+\r?$', board.command('sha256sum $g'), re.M)
        check(label + ' startup guard', guards == [sha(guard)])
        board.command('ir=/sys/bus/iio/devices')
        text = board.command('for node in $ir/iio:device*; do echo $node; cat $node/name; done')
        pairs = re.findall(r'(/sys/bus/iio/devices/iio:device[0-9]+)\r?\n([^\r\n]+)', text)
        check(label + ' RF names present and unique', all(sum(name == n for _, name in pairs) == 1 for n in RF_NAMES))
        names = {name: path for path, name in pairs}
        board.command('cd ' + names['cf-ad9361-lpc'])
        check(label + ' RX buffer idle', board.value('buffer/enable') == '0')
        check(label + ' RX scans idle', all(board.value('scan_elements/in_voltage' + str(i) + '_en') == '0'
                                           for i in range(4)))

    def source_check(label):
        board.command('src=' + args.remote)
        matches = re.findall(r'^([0-9a-f]{64})\s+\S+\r?$', board.command('sha256sum $src', timeout=12), re.M)
        check(label + ' compressed source SHA', matches == [args.expected_sha256])
        text = board.command('echo __BYTES__$(wc -c < $src)__END__')
        values = re.findall(r'^__BYTES__([0-9]+)__END__\r?$', text, re.M)
        check(label + ' compressed source size', values == [str(args.expected_bytes)])

    board = None
    (out / 'executed.py').write_bytes(Path(__file__).read_bytes())
    (out / 'S99board.guard').write_bytes(guard)
    save()
    try:
        board = RetrievalConsole(record, save, out)
        board.shell()
        inspect('before')
        source_check('before')
        record['status'] = 'reading_existing_compressed_chunks'
        save()
        parts = []
        for index, start in enumerate(range(0, args.expected_bytes, CHUNK_BYTES)):
            wanted_bytes = min(CHUNK_BYTES, args.expected_bytes - start)
            text = board.command(chunk_command(index, 'sha256sum'), timeout=12)
            matches = re.findall(r'^([0-9a-f]{64})\s+-\r?$', text, re.M)
            if len(matches) != 1:
                raise RuntimeError('missing/ambiguous board chunk SHA')
            wanted_sha = matches[0]
            row = dict(index=index, expected_bytes=wanted_bytes, sha256=wanted_sha, attempts=[])
            record['chunks'].append(row)
            save()
            if index in reused:
                chunk, prior_sha = reused[index]
                if prior_sha != wanted_sha:
                    raise RuntimeError('current board chunk differs from verified local prefix')
                target = out / ('chunk-' + str(index).zfill(3) + '.gzpart')
                target.write_bytes(chunk)
                parts.append(chunk)
                row.update(local_file=target.name, verified=True, reused_local_prefix=True)
                save()
                print('Reused verified local chunk ' + str(index + 1), flush=True)
                continue
            for attempt in range(1, 4):
                # Only this read transfer may be repeated; no capture or board writes.
                text = board.command(chunk_command(index, 'base64'), timeout=12, payload=True)
                try:
                    chunk = decode_payload(text, wanted_bytes)
                    if sha(chunk) != wanted_sha:
                        raise ValueError('chunk SHA mismatch')
                except (ValueError, binascii.Error) as error:
                    row['attempts'].append(dict(number=attempt, accepted=False, error=repr(error)))
                    save()
                    if attempt == 3:
                        raise RuntimeError('bounded transfer retries exhausted') from error
                else:
                    target = out / ('chunk-' + str(index).zfill(3) + '.gzpart')
                    with target.open('xb') as handle:
                        handle.write(chunk)
                    parts.append(chunk)
                    row.update(local_file=target.name, verified=True)
                    row['attempts'].append(dict(number=attempt, accepted=True))
                    save()
                    break
            print('Archived chunk ' + str(index + 1) + '/' + str((args.expected_bytes + CHUNK_BYTES - 1) // CHUNK_BYTES), flush=True)
        packed = b''.join(parts)
        record['status'] = 'checking_complete_local_bytes'
        save()
        raw = unpack_verified(packed, args.expected_bytes, args.expected_sha256,
                              args.raw_bytes, args.raw_sha256)
        with (out / 'source.gz').open('xb') as handle:
            handle.write(packed)
        raw_name = 'fb.raw' if args.remote.endswith('/fb.raw.gz') else 'iq-packed.bin'
        with (out / raw_name).open('xb') as handle:
            handle.write(raw)
        inspect('after')
        source_check('after')
        record.update(status='compressed_and_raw_bytes_archived_identity_and_source_rechecked',
                      local_compressed_file='source.gz', local_raw_file=raw_name,
                      compressed_sha256=sha(packed), compressed_bytes=len(packed),
                      verified_raw_sha256=sha(raw), verified_raw_bytes=len(raw))
    except Exception as error:
        record['failure_phase'] = record['status']
        record.update(status='incomplete_or_state_unconfirmed', error=repr(error))
        if board:
            try:
                record['passive_failure_tail'] = board.read(3)
            except Exception as tail_error:
                record['passive_tail_error'] = repr(tail_error)
    finally:
        if board:
            try:
                board.close()
            except Exception as close_error:
                record['serial_close_error'] = repr(close_error)
        record['serial_closed'] = board is None or 'serial_close_error' not in record
        record['ended_utc'] = datetime.now(timezone.utc).isoformat()
        save()
    print(out, flush=True)
    print(record['status'], flush=True)
    return 0 if record['status'] == 'compressed_and_raw_bytes_archived_identity_and_source_rechecked' else 1


if __name__ == '__main__':
    raise SystemExit(main())
