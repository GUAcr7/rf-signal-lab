"""Install the verified vendor Y2K22 additive patch and verify actual copies."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def main():
    source_report = sorted((ROOT / 'results').glob('p29-hls-patch-download-*/report.json'))[-1]
    source = json.loads(source_report.read_text('utf-8'))
    if source['status'] != 'downloaded_verified_zip_not_executed' or not source['final_url'].startswith('https://docs.amd.com/'):
        raise RuntimeError('verified vendor attachment missing')
    archive = Path(source['file'])
    if sha(archive) != source['sha256']:
        raise RuntimeError('download changed')
    install = Path('E:/FPGA_Tools/Xilinx')
    destination = install / 'y2k22_patch'
    review = Path('E:/FPGA_Tools/Work/p29-hls-review/y2k22_patch')
    targets = [install / name / '2021.1/common/scripts' for name in ['Vivado', 'Vitis_HLS']]
    out = ROOT / 'results' / datetime.now(timezone.utc).strftime('p29-hls-patch-install-%Y%m%dT%H%M%SZ')
    out.mkdir(exist_ok=False)
    baseline = [{'automg': str(t / 'automg.tcl'), 'sha256': sha(t / 'automg.tcl'),
                 'patch_before': sha(t / 'automg_patch_20220104.tcl')} for t in targets]
    if any(x['sha256'] is None or x['patch_before'] is not None for x in baseline):
        raise RuntimeError('unexpected existing/missing tool files; do not overwrite')
    with zipfile.ZipFile(archive) as z:
        for entry in z.infolist():
            if entry.is_dir():
                continue
            target = (install / entry.filename).resolve()
            if not target.is_relative_to(destination.resolve()):
                raise RuntimeError('unexpected archive path')
            raw = z.read(entry)
            if hashlib.sha256(raw).hexdigest() != sha(review / target.name):
                raise RuntimeError('reviewed patch copy changed')
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and target.read_bytes() != raw:
                raise RuntimeError('refusing different existing patch source')
            target.write_bytes(raw)
    record = dict(status='running', source=str(source_report), baseline=baseline,
                  board_operations=False, system_clock_changed=False)
    def save():
        (out / 'report.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    save()
    try:
        python = install / 'Vivado/2021.1/tps/win64/python-3.8.3/python.exe'
        with (out / 'stdout.txt').open('wb') as stdout, (out / 'stderr.txt').open('wb') as stderr:
            result = subprocess.run([str(python), 'y2k22_patch/patch.py'], cwd=install,
                                    stdout=stdout, stderr=stderr, timeout=60)
        record['exit_code'] = result.returncode
        expected = sha(review / 'automg_patch_20220104.tcl')
        record['installed'] = [dict(path=str(t / 'automg_patch_20220104.tcl'), sha256=sha(t / 'automg_patch_20220104.tcl')) for t in targets]
        if result.returncode != 0 or not all(row['sha256'] == expected for row in record['installed']):
            raise RuntimeError('vendor script did not install all verified copies')
        if any(sha(Path(row['automg'])) != row['sha256'] for row in baseline):
            raise RuntimeError('unexpected original automg.tcl mutation')
        if (install / 'y2k22_patch.log').is_file():
            shutil.copy2(install / 'y2k22_patch.log', out / 'vendor-patch.log')
        record['status'] = 'additive_vendor_patch_installed_hash_verified'
    except Exception as error:
        record.update(status='failed', error=repr(error))
        raise
    finally:
        save()
        print(out)


if __name__ == '__main__':
    main()
