"""Prepare validated untrained CNN operator checks for actual ARM execution."""
import hashlib
import json
import subprocess
import tarfile
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
from rfsig.tiny_cnn_probe import infer_counts

ROOT=Path(__file__).resolve().parents[1]
STAMP=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
OUT=ROOT/'results'/('p06-cnn-probe-'+STAMP)
PREFIX='cnn-probe-'+STAMP
COMPILER=Path('E:/FPGA_Tools/ARM-GNU-A-8.3-2019.03/attempt-2/gcc-arm-8.3-2019.03-x86_64-arm-linux-gnueabihf/bin/arm-linux-gnueabihf-gcc')

def lp(p):
    s=p.resolve().as_posix(); return '/mnt/'+s[0].lower()+s[2:]

def command(name,argv):
    run=subprocess.run(argv,capture_output=True,timeout=180)
    (OUT/(name+'.stdout.txt')).write_bytes(run.stdout)
    (OUT/(name+'.stderr.txt')).write_bytes(run.stderr)
    if run.returncode: raise RuntimeError(f'{name} exited {run.returncode}')
    return run.stdout.decode(errors='replace')

def main():
    OUT.mkdir(); bundle=OUT/PREFIX; (bundle/'inputs').mkdir(parents=True); (bundle/'bin').mkdir()
    source=ROOT/'embedded/tiny_cnn_probe/tiny_cnn_probe.c'
    (bundle/'tiny_cnn_probe.c').write_bytes(source.read_bytes())
    flags=['-std=c99','-O2','-Wall','-Wextra','-Werror','-fno-fast-math','-ffp-contract=off']
    host=OUT/'host-probe.exe'
    command('host-compile',['C:/msys64/ucrt64/bin/gcc.exe',*flags,str(source),'-o',str(host)])
    binary=bundle/'bin/tiny-cnn-probe'
    command('arm-compile',['wsl.exe','-d','Ubuntu-24.04','--exec',lp(COMPILER),*flags,'-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard','-marm',lp(source),'-o',lp(binary),'-lrt'])
    readelf=COMPILER.with_name('arm-linux-gnueabihf-readelf')
    elf=command('arm-elf',['wsl.exe','-d','Ubuntu-24.04','--exec',lp(readelf),'-h','-A','-l','-d','-V',lp(binary)])
    assert 'ELF32' in elf and 'Machine:                           ARM' in elf
    assert '/lib/ld-linux-armhf.so.3' in elf and 'VFP registers' in elf
    fixtures=[]
    vector_root=ROOT/'results/p07-arm-board-bundle-20261011/arm-fir-check/vectors'
    for directory in sorted(vector_root.iterdir()):
        components=[]
        for name in ['input_i.hex','input_q.hex']:
            words=np.array([int(s,16) for s in (directory/name).read_text().splitlines()],dtype=np.int32)
            components.append(np.where(words>=2048,words-4096,words))
        counts=np.zeros((1024,2),dtype=np.int16)
        size=min(1024,len(components[0]))
        counts[:size]=np.array(components).T[:size]
        path=bundle/'inputs'/(directory.name+'.iq')
        path.write_bytes(counts.astype('<i2').tobytes())
        expected=infer_counts(counts)
        output=command('host-'+directory.name,[str(host),str(path)])
        actual=np.fromstring(output.strip(),sep=',')
        np.testing.assert_allclose(actual,expected,rtol=0,atol=2e-6)
        fixtures.append({'name':directory.name,'source_samples_used':size,'zero_pad':1024-size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'expected':expected.tolist(),'host_max_absolute_error':float(np.max(np.abs(actual-expected)))})
    bad=OUT/'bad.iq'; bad.write_bytes(np.full((1024,2),2048,dtype='<i2').tobytes())
    assert subprocess.run([str(host),str(bad)],capture_output=True).returncode!=0
    malformed=OUT/'short.iq'; malformed.write_bytes(b'\0\0')
    assert subprocess.run([str(host),str(malformed)],capture_output=True).returncode!=0
    (bundle/'expected.json').write_text(json.dumps(fixtures,indent=2))
    run=['#!/bin/sh','set -eu','cd "$(dirname "$0")"','test ! -e outputs','sha256sum -c SHA256SUMS','mkdir outputs','uname -a > outputs/uname.txt']
    for case in fixtures:
        n=case['name']; run += [f'./bin/tiny-cnn-probe inputs/{n}.iq > outputs/{n}.txt']
    assert 'qpsk' in {case['name'] for case in fixtures}
    run += ['./bin/tiny-cnn-probe inputs/qpsk.iq --bench > outputs/benchmark.txt','echo CNN_OPERATOR_RUN_DONE_UNTRAINED']
    (bundle/'run.sh').write_text('\n'.join(run)+'\n',newline='\n')
    sums=[]
    for path in sorted(bundle.rglob('*')):
        if path.is_file(): sums.append(hashlib.sha256(path.read_bytes()).hexdigest()+'  '+path.relative_to(bundle).as_posix())
    (bundle/'SHA256SUMS').write_text('\n'.join(sums)+'\n',newline='\n')
    archive=OUT/(PREFIX+'.tar')
    with tarfile.open(archive,'w') as tar:
        for path in sorted(bundle.rglob('*')):
            if path.is_file():
                info=tar.gettarinfo(str(path),arcname=PREFIX+'/'+path.relative_to(bundle).as_posix()); info.mode=0o755 if path.parent.name=='bin' else 0o644
                with path.open('rb') as f: tar.addfile(info,f)
    report={'status':'host_reference_passed_ARM_pending','untrained':True,'cases':fixtures,'operators':['valid_conv1d_stride2','relu','global_average_pool','dense_logits'],'parameters':115,'input_contract':'1024x2 signed12 LE16 /2048','SNR':'not_applicable_operator_fixture','accuracy':'not_measured_untrained','quantization':'not_performed','absolute_tolerance':2e-6,'archive':str(archive),'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'prefix':PREFIX,'compiler_flags':flags,'arm_binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest()}
    (OUT/'report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({'out':str(OUT),'archive':str(archive),'sha256':report['archive_sha256'],'prefix':PREFIX,'cases':len(fixtures)}))

if __name__=='__main__': main()
