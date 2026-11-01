"""Cross-compile a bounded native IIO receive probe; preserve original firmware."""
import hashlib,json,subprocess,tarfile
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
STAMP=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
OUT=ROOT/'results'/('p06-native-rx-'+STAMP)
PREFIX='native-rx-'+STAMP
TOOL=Path('E:/FPGA_Tools/ARM-GNU-A-8.3-2019.03/attempt-2/gcc-arm-8.3-2019.03-x86_64-arm-linux-gnueabihf/bin')
def lp(p):
    s=p.resolve().as_posix();return '/mnt/'+s[0].lower()+s[2:]
def main():
    OUT.mkdir();bundle=OUT/PREFIX;(bundle/'bin').mkdir(parents=True)
    source=ROOT/'embedded/arm_rx_probe/arm_rx_probe.c';header=ROOT/'embedded/vendor/libiio-v0.24/iio.h'
    source_manifest=json.loads((header.parent/'source.json').read_text(encoding='utf-8-sig'))
    assert hashlib.sha256(header.read_bytes()).hexdigest()==source_manifest['sha256']
    binary=bundle/'bin/arm-rx-probe'
    flags=['-std=c11','-O2','-Wall','-Wextra','-Werror','-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard','-marm']
    argv=['wsl.exe','-d','Ubuntu-24.04','--exec',lp(TOOL/'arm-linux-gnueabihf-gcc'),*flags,'-I',lp(header.parent),lp(source),'-o',lp(binary),'-ldl','-lrt']
    result=subprocess.run(argv,capture_output=True,timeout=180)
    (OUT/'compile.stdout.txt').write_bytes(result.stdout);(OUT/'compile.stderr.txt').write_bytes(result.stderr)
    if result.returncode:raise RuntimeError(f'Compile exit {result.returncode}')
    elf=subprocess.run(['wsl.exe','-d','Ubuntu-24.04','--exec',lp(TOOL/'arm-linux-gnueabihf-readelf'),'-h','-A','-l','-d','-V',lp(binary)],capture_output=True,timeout=60)
    assert elf.returncode==0
    (OUT/'elf.txt').write_bytes(elf.stdout);(OUT/'elf.stderr.txt').write_bytes(elf.stderr)
    text=elf.stdout.decode();assert 'ELF32' in text and 'VFP registers' in text and '/lib/ld-linux-armhf.so.3' in text
    (bundle/source.name).write_bytes(source.read_bytes());(bundle/'iio.h').write_bytes(header.read_bytes());(bundle/'libiio-header-source.json').write_bytes((header.parent/'source.json').read_bytes())
    (bundle/'run.sh').write_text('#!/bin/sh\nset -eu\ncd "$(dirname "$0")"\ntest ! -e outputs\nsha256sum -c SHA256SUMS\nmkdir outputs\nuname -a > outputs/uname.txt\n./bin/arm-rx-probe outputs > outputs/run.txt\ncat outputs/run.txt\n',newline='\n')
    sums=[hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.relative_to(bundle).as_posix() for p in sorted(bundle.rglob('*')) if p.is_file()]
    (bundle/'SHA256SUMS').write_text('\n'.join(sums)+'\n',newline='\n')
    archive=OUT/(PREFIX+'.tar')
    with tarfile.open(archive,'w') as tar:
        for p in sorted(bundle.rglob('*')):
            if p.is_file():
                info=tar.gettarinfo(str(p),arcname=PREFIX+'/'+p.relative_to(bundle).as_posix());info.mode=0o755 if p.parent.name=='bin' else 0o644
                with p.open('rb') as f:tar.addfile(info,f)
    report={'status':'cross_compile_passed_board_pending','prefix':PREFIX,'archive':str(archive),'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'header':source_manifest,'compiler_argv':argv,'RF_writes':False,'sessions':{'1':{'blocks':8,'block_samples':4096},'2':{'blocks':4,'block_samples':1024}},'hardware_gaps':'unknown','purpose':'native ARM RX snapshots, release and recreate, integer statistics'}
    (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'out':str(OUT),'archive':str(archive),'prefix':PREFIX,'sha256':report['archive_sha256']}))
if __name__=='__main__':main()
