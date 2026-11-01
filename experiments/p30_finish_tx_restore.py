"""Continue the hash-verified upload using this BusyBox's supported plain tar."""
from datetime import datetime,timezone
import gzip
import hashlib
import json
from pathlib import Path
import re
from p22_acquire_comparison import Console,ROOT


def main():
    parent=ROOT/'results/p30-tx-file-restore-20261019T132637Z'
    prior=json.loads((parent/'report.json').read_text('utf-8'))
    upload=json.loads((parent/'upload/report.json').read_text('utf-8-sig'))
    payload=parent/'verified-recovery.tar.gz'
    if hashlib.sha256(payload.read_bytes()).hexdigest()!=prior['payload_sha256'] or not upload['tty_restored']:
        raise RuntimeError('upload evidence not accepted')
    if upload['status']!='serial_upload_checksum_passed_no_code_executed':raise RuntimeError('unverified upload')
    directory=prior['remote_directory']
    if not re.fullmatch(r'/tmp/p12-source-stage-p30-[0-9]{6}',directory):raise ValueError('unexpected directory')
    uncompressed=gzip.decompress(payload.read_bytes())
    tar_hash=hashlib.sha256(uncompressed).hexdigest()
    out=ROOT/'results'/('p30-tx-file-verification-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    out.mkdir(exist_ok=False)
    report=dict(status='running',stages=[],parent=str(parent/'report.json'),remote_directory=directory,
        RF_transmitted=False,RF_configuration_writes=False,firmware_writes=False,uncompressed_tar_sha256=tar_hash)
    def save():(out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    save();console=None
    try:
        console=Console('COM9',report,save)
        if 'Linux pzp201' not in console.command('uname -a'):raise RuntimeError('wrong board')
        boot=console.command('cat /proc/sys/kernel/random/boot_id')
        bootid=re.search(r'[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}',boot)[0]
        if bootid not in prior['boot_id_output']:raise RuntimeError('board rebooted since upload')
        report['boot_id']=bootid
        console.command('cd '+directory)
        if prior['payload_sha256'] not in console.command('sha256sum source.tar.gz'):raise RuntimeError('remote upload changed')
        console.command('command -v gzip')
        console.command('test ! -e source.tar')
        console.command('gzip -dc source.tar.gz > source.tar')
        if tar_hash not in console.command('sha256sum source.tar'):raise RuntimeError('decompression byte mismatch')
        console.command('test ! -e stage')
        console.command('tar -xf source.tar')
        console.command('cd stage')
        console.command('chmod 755 arm/arm-tx-source')
        sums=console.command('sha256sum -c SHA256SUMS')
        if sum(line.endswith(': OK') for line in sums.splitlines())!=8:raise RuntimeError('package check count mismatch')
        inspect=console.command('./arm/arm-tx-source --inspect')
        if 'INSPECT_PASS read_only=true no_buffers_created=true' not in inspect:raise RuntimeError('inspect incomplete')
        report['inspect_output']=inspect
        report['checked']=[]
        for name,digest in prior['stage_files'].items():
            if not name.endswith('.iq16le'):continue
            console.command('p='+name[len('stage/'):]);console.command('h='+digest)
            result=console.command('./arm/arm-tx-source --check $p 131072 $h')
            if 'INPUT_CHECK_PASS' not in result:raise RuntimeError('file check incomplete')
            report['checked'].append(name);save()
        console.command('cd ../bundle')
        console.command('sha256sum -c SHA256SUMS')
        for name,digest in prior['modulation_files'].items():
            if not name.endswith('.iq16le'):continue
            console.command('p='+name);console.command('h='+digest)
            result=console.command('../stage/arm/arm-tx-source --check $p 131072 $h')
            if 'INPUT_CHECK_PASS' not in result:raise RuntimeError('modulation check incomplete')
            report['checked'].append('bundle/'+name);save()
        console.command('ps')
        if len(report['checked'])!=9:raise RuntimeError('expected nine waveform checks')
        report['status']='RAM_files_eight_checksums_nine_waveforms_and_inspect_verified'
    except Exception as error:report.update(status='failed',error=repr(error))
    finally:
        if console:console.close()
        save();print(out);print(report['status'])
    return 0 if report['status'].endswith('_verified') else 1


if __name__=='__main__':raise SystemExit(main())
