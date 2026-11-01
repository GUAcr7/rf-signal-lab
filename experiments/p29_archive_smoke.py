"""Read back the already captured, receive-only P29 sparse smoke bytes and final state."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from p26_retrieve_chunks import ChunkConsole, decode_payload, ROOT


def main():
    source = ROOT / 'results/p27-smoke-20261019T082709Z/report.json'
    smoke = json.loads(source.read_text('utf-8'))
    if smoke['RF_transmitted'] or smoke['status'] != 'receiver_abi_layout_capture_and_release_verified':
        raise RuntimeError('not the expected receive-only smoke')
    out = ROOT / 'results' / datetime.now(timezone.utc).strftime('p29-smoke-archive-%Y%m%dT%H%M%SZ')
    out.mkdir(exist_ok=False)
    report = dict(created_utc=datetime.now(timezone.utc).isoformat(), source=str(source),
                  stages=[], read_only=True, RF_transmitted=False,
                  status='in_progress', diagnostic_only=True, complete_stream_saved=False,
                  lossless_proven=False)
    def save():
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    save()
    console = None
    try:
        console = ChunkConsole('COM8', report, save)
        if 'Zynq-Tronlong' not in console.command('uname -a'):
            raise RuntimeError('wrong board')
        directory = smoke['output_directory']
        if not re.fullmatch(r'/tmp/p27-smoke-[0-9]{6}', directory):
            raise RuntimeError('unexpected capture path')
        console.command('p=' + directory + '/prefixes.bin')
        digest = re.search(r'^([0-9a-f]{64})\s', console.command('sha256sum $p'), re.M)[1]
        original = next(s for s in smoke['stages'] if s['command'] == 'sha256sum prefixes.bin')
        if digest not in original['output']:
            raise RuntimeError('saved diagnostic file changed')
        meta = smoke['native_metadata']
        expected = meta['blocks'] * meta['kept_frames_per_block'] * meta['channels'] * 2
        raw = decode_payload(console.command('base64 $p', timeout=25), expected)
        if hashlib.sha256(raw).hexdigest() != digest:
            raise RuntimeError('readback digest mismatch')
        (out / 'prefixes.bin').write_bytes(raw)
        (out / 'metadata.json').write_text(json.dumps(meta, indent=2) + '\n', encoding='utf-8')
        report['raw'] = dict(file='prefixes.bin', bytes=len(raw), sha256=digest,
                             saved_fraction=0.015625, channels=2, source_format=meta['source_format'])
        for command in ['cat /etc/board-mode', '/etc/rcS.d/S99board --check-rf',
                        'cat /proc/sys/kernel/random/boot_id', 'ps -ef',
                        'cat /sys/bus/iio/devices/iio:device*/name']:
            console.command(command, timeout=6)
        console.close()
        console = ChunkConsole('COM9', report, save)
        if 'Linux pzp201' not in console.command('uname -a'):
            raise RuntimeError('wrong old board')
        processes = console.command('ps')
        if any('arm-tx-source --run' in row and 'grep' not in row for row in processes.splitlines()):
            raise RuntimeError('unexpected active TX')
        console.command('cat /proc/sys/kernel/random/boot_id')
        report['status'] = 'raw_bytes_and_final_board_identity_verified'
    except Exception as error:
        report.update(status='failed', error=repr(error))
        raise
    finally:
        if console:
            console.close()
        save()
        print(out)


if __name__ == '__main__':
    main()
