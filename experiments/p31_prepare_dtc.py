"""Keep a checksum-pinned MSYS2 DTC in E:, without changing installed packages."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
PACKAGES=[('dtc','mingw-w64-ucrt-x86_64-dtc-1.8.1-1-any.pkg.tar.zst','0f3c4df43133b99e040f7d42666e36e50c9aea2f59a494e0aad3b475f3fdd32d'),
    ('libyaml','mingw-w64-ucrt-x86_64-libyaml-0.2.5-2-any.pkg.tar.zst','bf4c28a3a92a46db3c809b0789aef731ae9a0c4283db368c7e8624550fed07f3')]


def main():
    out=ROOT/'results'/('p31-dtc-tools-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(exist_ok=False)
    target=Path('E:/FPGA_Tools/Utilities/dtc-1.8.1-ucrt64');target.mkdir(parents=True,exist_ok=False)
    report=dict(status='running',target=str(target),packages=[],files=[],board_operations=False,global_packages_modified=False,
        primary_metadata=['https://packages.msys2.org/packages/mingw-w64-ucrt-x86_64-dtc','https://packages.msys2.org/packages/mingw-w64-ucrt-x86_64-libyaml'])
    def save():(out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    save()
    try:
        for name,filename,expected in PACKAGES:
            url='https://mirror.msys2.org/mingw/ucrt64/'+filename
            with urllib.request.urlopen(url,timeout=45) as response:data=response.read(3*1024*1024)
            if hashlib.sha256(data).hexdigest()!=expected:raise RuntimeError('package checksum mismatch '+name)
            path=out/filename;path.write_bytes(data)
            tarpath=out/(name+'.tar')
            command=['C:/msys64/ucrt64/bin/zstd.exe','-d',str(path),'-o',str(tarpath)]
            result=subprocess.run(command,capture_output=True,timeout=45);(out/(name+'-decompress.txt')).write_bytes(result.stdout+result.stderr)
            if result.returncode:raise RuntimeError('zstd failed')
            report['packages'].append(dict(url=url,sha256=expected,bytes=len(data)))
            with tarfile.open(tarpath) as archive:
                for member in archive.getmembers():
                    if not member.isfile():continue
                    selected=member.name.startswith('ucrt64/bin/') and member.name.rsplit('/',1)[1] in ['dtc.exe','fdtoverlay.exe','fdtget.exe','fdtdump.exe','libfdt-1.dll','libyaml-0-2.dll']
                    licensed=member.name.startswith('ucrt64/share/licenses/') or member.name=='.PKGINFO'
                    if not (selected or licensed):continue
                    dest=target/member.name if selected or member.name.startswith('ucrt64/') else out/(name+'-PKGINFO.txt')
                    if not dest.resolve().is_relative_to(target.resolve()) and dest.parent!=out:raise ValueError('unsafe member path')
                    dest.parent.mkdir(parents=True,exist_ok=True)
                    payload=archive.extractfile(member).read();dest.write_bytes(payload)
                    report['files'].append(dict(path=str(dest),sha256=hashlib.sha256(payload).hexdigest()))
            save()
        executable=target/'ucrt64/bin/dtc.exe'
        result=subprocess.run([str(executable),'--version'],capture_output=True,timeout=10)
        version=(result.stdout+result.stderr).decode('utf-8',errors='replace')
        (out/'version.txt').write_text(version,encoding='utf-8')
        if result.returncode or 'DTC 1.8.1' not in version:raise RuntimeError('native DTC version failed '+version)
        report.update(status='pinned_native_dtc_and_libfdt_available',version=version.strip())
        (ROOT/'results/p31-dtc-active.json').write_text(json.dumps(dict(bin=str(executable.parent),evidence=str(out/'report.json')),indent=2)+'\n',encoding='utf-8')
    except Exception as error:report.update(status='failed',error=repr(error))
    finally:save()
    print(out);print(report['status'])
    if 'error' in report:print(report['error'])
    return 0 if report['status'].endswith('_available') else 1


if __name__=='__main__':raise SystemExit(main())
