"""Archive a specified fresh receive-only smoke and check the re-powered boot."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
from p26_retrieve_chunks import ChunkConsole,decode_payload,ROOT


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('--boot-id',required=True)
    args=parser.parse_args()
    source=args.source.resolve()
    if not source.is_relative_to((ROOT/'results').resolve()):raise ValueError('expected local evidence file')
    smoke=json.loads(source.read_text('utf-8'))
    if smoke['RF_transmitted'] or smoke['status']!='receiver_abi_layout_capture_and_release_verified':
        raise ValueError('unaccepted receive-only smoke')
    out=ROOT/'results'/('p30-smoke-archive-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    out.mkdir(exist_ok=False)
    report=dict(status='running',source=str(source),stages=[],read_only=True,RF_transmitted=False,
        diagnostic_only=True,complete_stream_saved=False,lossless_proven=False,expected_boot_id=args.boot_id)
    console=None
    def save():(out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    save()
    try:
        console=ChunkConsole('COM8',report,save)
        if 'Zynq-Tronlong' not in console.command('uname -a'):raise RuntimeError('wrong receiver')
        if args.boot_id not in console.command('cat /proc/sys/kernel/random/boot_id'):raise RuntimeError('receiver rebooted again')
        directory=smoke['output_directory']
        if not re.fullmatch(r'/tmp/p27-smoke-[0-9]{6}',directory):raise ValueError('unexpected capture path')
        console.command('p='+directory+'/prefixes.bin')
        digest=re.search(r'^([0-9a-f]{64})\s',console.command('sha256sum $p'),re.M)[1]
        original=next(s for s in smoke['stages'] if s['command']=='sha256sum prefixes.bin')
        if digest not in original['output']:raise RuntimeError('capture changed after smoke')
        meta=smoke['native_metadata']
        expected=meta['blocks']*meta['kept_frames_per_block']*meta['channels']*2
        raw=decode_payload(console.command('base64 $p',timeout=25),expected)
        if hashlib.sha256(raw).hexdigest()!=digest:raise RuntimeError('host readback digest mismatch')
        (out/'prefixes.bin').write_bytes(raw)
        (out/'metadata.json').write_text(json.dumps(meta,indent=2)+'\n',encoding='utf-8')
        for command in ['cat /proc/sys/kernel/random/boot_id','/etc/rcS.d/S99board --check-rf','ps -ef']:
            console.command(command)
        report.update(status='fresh_sparse_bytes_boot_identity_and_release_verified',raw=dict(bytes=len(raw),sha256=digest,saved_fraction=.015625,channels=2))
    except Exception as error:report.update(status='failed',error=repr(error))
    finally:
        if console:console.close()
        save();print(out);print(report['status'])
    return 0 if report['status'].endswith('_verified') else 1


if __name__=='__main__':raise SystemExit(main())
