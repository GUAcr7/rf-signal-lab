"""Restore verified RAM-only TX tools/waveforms and inspect; never transmit."""
from datetime import datetime,timezone
import hashlib
import io
import json
from pathlib import Path,PurePosixPath
import subprocess
import tarfile
from p22_acquire_comparison import Console,ROOT


def sha(data):return hashlib.sha256(data).hexdigest()


def main():
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out=ROOT/'results'/('p30-tx-file-restore-'+stamp);out.mkdir(exist_ok=False)
    original=ROOT/'results/p13-upload-bundle-20261017T025802Z/board-session-bundle.tar'
    if sha(original.read_bytes())!='9af83ce980e9aa78214b6d50b170229564cf4e14940b1919d04a311c04afde9e':
        raise RuntimeError('original recovery bundle changed')
    payload=out/'verified-recovery.tar.gz'
    stage_files={};mod_files={}
    original_mods=ROOT/'results/p21-mod-waveforms-20261017T122536Z'
    original_manifest=json.loads((original_mods/'report.json').read_text('utf-8'))
    expected_mods={entry['file']:entry['raw_sha256'] for entry in original_manifest['waveforms']}
    canonical_manifest=''.join(digest+'  '+name+'\n' for name,digest in expected_mods.items()).encode('ascii')
    old_manifest=(original_mods/'bundle/SHA256SUMS').read_bytes()
    if old_manifest.replace(b'\r\n',b'\n')!=canonical_manifest:
        raise RuntimeError('original modulation manifest contents differ from reviewed report')
    with tarfile.open(original,'r:') as old,tarfile.open(payload,'w:gz') as new:
        for member in old.getmembers():
            name=PurePosixPath(member.name)
            if name.is_absolute() or '..' in name.parts or name.parts[0]!='stage' or not(member.isfile() or member.isdir()):
                raise ValueError('unexpected original tar member')
            if member.isdir():new.addfile(member)
            else:
                data=old.extractfile(member).read();new.addfile(member,io.BytesIO(data));stage_files[member.name]=sha(data)
        for name in ['bpsk.iq16le','qpsk.iq16le','qam16.iq16le','SHA256SUMS']:
            source=original_mods/'bundle'/name
            data=canonical_manifest if name=='SHA256SUMS' else source.read_bytes()
            if name!='SHA256SUMS' and sha(data)!=expected_mods[name]:raise ValueError('reviewed modulation bytes changed')
            entry=tarfile.TarInfo('bundle/'+name);entry.size=len(data);entry.mode=0o644
            new.addfile(entry,io.BytesIO(data));mod_files[name]=sha(data)
    remote='/tmp/p12-source-stage-p30-'+stamp[9:15]
    report=dict(status='prepared',created_utc=datetime.now(timezone.utc).isoformat(),stages=[],
        original_bundle=str(original),payload_sha256=sha(payload.read_bytes()),payload_bytes=payload.stat().st_size,
        stage_files=stage_files,modulation_files=mod_files,remote_directory=remote,
        modulation_manifest_lf_correction=dict(original_sha256=sha(old_manifest),new_sha256=sha(canonical_manifest),original_modified=False),
        RF_transmitted=False,RF_configuration_writes=False,firmware_writes=False,ram_files_restored=True)
    def save():(out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    save();console=None
    try:
        # Existing uploader retains its own serial transcript, byte hash and TTY
        # restoration. Credentials are not put in this evidence record.
        command=['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'experiments/p12_serial_upload.ps1'),
            '-Port','COM9','-InputFile',str(payload),'-ExpectedSha256',report['payload_sha256'],
            '-BoardDirectory',remote,'-EvidenceDirectory',str(out/'upload'),'-LoginPassword','analog']
        with (out/'upload-output.txt').open('wb') as log:
            result=subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=450)
        upload=json.loads((out/'upload/report.json').read_text('utf-8-sig'))
        if result.returncode or upload['status']!='serial_upload_checksum_passed_no_code_executed' or not upload['tty_restored']:
            raise RuntimeError('uploader or TTY restoration did not pass')
        console=Console('COM9',report,save)
        if 'Linux pzp201' not in console.command('uname -a'):raise RuntimeError('wrong old board')
        report['boot_id_output']=console.command('cat /proc/sys/kernel/random/boot_id')
        console.command('cd '+remote)
        console.command('command -v gzip')
        console.command('gzip -dc source.tar.gz > source.tar')
        console.command('tar -xf source.tar')
        console.command('cd stage')
        console.command('chmod 755 arm/arm-tx-source')
        sums=console.command('sha256sum -c SHA256SUMS')
        if sum(line.endswith(': OK') for line in sums.splitlines())!=8:raise RuntimeError('expected eight package checks')
        inspect=console.command('./arm/arm-tx-source --inspect')
        if 'INSPECT_PASS read_only=true no_buffers_created=true' not in inspect:raise RuntimeError('read-only inspect incomplete')
        report['inspect_output']=inspect
        checked=[]
        for filename,digest in stage_files.items():
            if not filename.endswith('.iq16le'):continue
            path=filename[len('stage/'):]
            console.command('p='+path);console.command('h='+digest)
            result=console.command('./arm/arm-tx-source --check $p 131072 $h')
            if 'INPUT_CHECK_PASS' not in result:raise RuntimeError('waveform check missing')
            checked.append(path)
        console.command('cd ../bundle')
        console.command('sha256sum -c SHA256SUMS')
        for name,digest in mod_files.items():
            if not name.endswith('.iq16le'):continue
            console.command('p='+name);console.command('h='+digest)
            result=console.command('../stage/arm/arm-tx-source --check $p 131072 $h')
            if 'INPUT_CHECK_PASS' not in result:raise RuntimeError('modulation waveform check missing')
            checked.append('bundle/'+name)
        report.update(status='RAM_files_hashes_nine_waveforms_and_read_only_inspect_verified',checked=checked)
    except Exception as error:report.update(status='failed',error=repr(error))
    finally:
        if console:console.close()
        save();print(out);print(report['status'])
    return 0 if report['status'].endswith('_verified') else 1


if __name__=='__main__':raise SystemExit(main())
