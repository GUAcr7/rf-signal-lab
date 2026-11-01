"""Retrieve a frozen sparse RX file in small, hash-checked, bounded retries."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from p26_retrieve_chunks import ChunkConsole, decode_payload, ROOT


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('--boot-id',required=True)
    args=parser.parse_args()
    source=args.source.resolve()
    if not source.is_relative_to(ROOT/'results'):
        raise ValueError('source must be local evidence')
    smoke=json.loads(source.read_text('utf-8'))
    if smoke['status']!='receiver_abi_layout_capture_and_release_verified' or smoke['RF_transmitted']:
        raise ValueError('unaccepted receive-only smoke')
    directory=smoke['output_directory']
    if not re.fullmatch(r'/tmp/p27-smoke-[0-9]{6}',directory):
        raise ValueError('unexpected board path')
    meta=smoke['native_metadata']
    total=meta['blocks']*meta['kept_frames_per_block']*meta['channels']*2
    original=next(s for s in smoke['stages'] if s['command']=='sha256sum prefixes.bin')
    expected=re.search(r'^([0-9a-f]{64})\s',original['output'],re.M)[1]
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p31-sparse-archive-%Y%m%dT%H%M%SZ')
    out.mkdir(exist_ok=False)
    record=dict(status='reading',stages=[],chunks=[],source=str(source),boot_id=args.boot_id,
        chunk_bytes=4096,max_attempts_per_chunk=3,RF_transmitted=False,board_file_writes=False,
        complete_stream_saved=False,lossless_proven=False)

    def save():
        (out/'report.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')

    def digest(board,command):
        return re.search(r'^([0-9a-f]{64})\s',board.command(command),re.M)[1]

    board=None
    save()
    try:
        board=ChunkConsole('COM8',record,save)
        if 'Zynq-Tronlong' not in board.command('uname -a') or args.boot_id not in board.command('cat /proc/sys/kernel/random/boot_id'):
            raise RuntimeError('wrong receiver/session')
        board.command('p='+directory+'/prefixes.bin')
        if digest(board,'sha256sum $p')!=expected:
            raise RuntimeError('source changed after smoke')
        raw=bytearray()
        for index,start in enumerate(range(0,total,4096)):
            prefix=f'dd if=$p bs=4096 skip={index} count=1 2>/dev/null'
            wanted=digest(board,prefix+' | sha256sum')
            row=dict(index=index,sha256=wanted,attempts=[])
            record['chunks'].append(row)
            for attempt in range(1,4):
                output=board.command(prefix+' | base64',timeout=8)
                try:
                    chunk=decode_payload(output,min(4096,total-start))
                    if hashlib.sha256(chunk).hexdigest()!=wanted:
                        raise ValueError('chunk hash mismatch')
                except (ValueError, __import__('binascii').Error) as error:
                    row['attempts'].append(dict(number=attempt,accepted=False,error=repr(error)))
                    save()
                    if attempt==3:
                        raise RuntimeError('bounded chunk retries exhausted') from error
                else:
                    row['attempts'].append(dict(number=attempt,accepted=True))
                    (out/f'chunk{index:03d}.bin').write_bytes(chunk)
                    raw.extend(chunk)
                    save()
                    break
        if len(raw)!=total or hashlib.sha256(raw).hexdigest()!=expected or digest(board,'sha256sum $p')!=expected:
            raise RuntimeError('assembled or final source hash mismatch')
        (out/'prefixes.bin').write_bytes(raw)
        (out/'metadata.json').write_text(json.dumps(meta,indent=2)+'\n',encoding='utf-8')
        board.command('/etc/rcS.d/S99board --check-rf')
        record.update(status='fresh_sparse_bytes_boot_identity_and_release_verified',
            raw=dict(bytes=len(raw),sha256=expected,saved_fraction=meta['kept_frames_per_block']/meta['dma_frames'],channels=meta['channels']))
    except Exception as error:
        record.update(status='failed',error=repr(error))
    finally:
        if board:
            board.close()
        record['serial_closed']=True
        save()
    print(out)
    print(record['status'])
    return 1 if record['status']=='failed' else 0


if __name__=='__main__':raise SystemExit(main())
