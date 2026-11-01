"""Freeze desktop baseline into portable C and compare before ARM deployment."""
import argparse,hashlib,json,subprocess,tarfile
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
from rfsig.modulation_baseline import features

def lp(path):s=path.resolve().as_posix();return '/mnt/'+s[0].lower()+s[2:]
def main():
    p=argparse.ArgumentParser();p.add_argument('trained',type=Path);a=p.parse_args()
    root=Path(__file__).resolve().parents[1];stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');prefix='baseline-arm-'+stamp;out=root/'results'/('p10-baseline-arm-'+stamp);out.mkdir();bundle=out/prefix;(bundle/'inputs').mkdir(parents=True);(bundle/'bin').mkdir()
    trained=json.loads((a.trained/'report.json').read_text());model=a.trained/'linear-model.npz'
    assert hashlib.sha256(model.read_bytes()).hexdigest()==trained['model_sha256']
    with np.load(model,allow_pickle=False) as z:w=z['weights'];b=z['bias'];mean=z['feature_mean'];scale=z['feature_scale']
    assert w.shape==(14,3) and b.shape==(3,) and mean.shape==scale.shape==(14,) and (scale>0).all()
    lines=['/* Frozen synthetic traditional baseline; source hash '+trained['model_sha256']+' */']
    for name,array in [('model_weights',w),('model_bias',b),('model_mean',mean),('model_scale',scale)]:
        if array.ndim==2:lines.append('static const double '+name+'[14][3]={'+','.join('{'+','.join(format(float(v),'.17g') for v in row)+'}' for row in array)+'};')
        else:lines.append('static const double '+name+'['+str(len(array))+']={'+','.join(format(float(v),'.17g') for v in array)+'};')
    (bundle/'model.h').write_text('\n'.join(lines)+'\n',newline='\n')
    source=root/'embedded/modulation_baseline/baseline_infer.c';(bundle/source.name).write_bytes(source.read_bytes());host=out/'baseline-host.exe';binary=bundle/'bin/baseline-infer'
    flags=['-std=c99','-O2','-Wall','-Wextra','-Werror','-Wno-misleading-indentation','-fno-fast-math','-ffp-contract=off']
    def run(label,argv):
        r=subprocess.run(argv,capture_output=True,timeout=180);(out/(label+'.stdout.txt')).write_bytes(r.stdout);(out/(label+'.stderr.txt')).write_bytes(r.stderr)
        if r.returncode:raise RuntimeError(f'{label}: {r.returncode}')
        return r.stdout.decode()
    run('host-compile',['C:/msys64/ucrt64/bin/gcc.exe',*flags,'-I',str(bundle),str(source),'-o',str(host),'-lm'])
    tool=Path('E:/FPGA_Tools/ARM-GNU-A-8.3-2019.03/attempt-2/gcc-arm-8.3-2019.03-x86_64-arm-linux-gnueabihf/bin')
    run('arm-compile',['wsl.exe','-d','Ubuntu-24.04','--exec',lp(tool/'arm-linux-gnueabihf-gcc'),*flags,'-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard','-marm','-I',lp(bundle),lp(source),'-o',lp(binary),'-lm','-lrt'])
    elf=run('arm-elf',['wsl.exe','-d','Ubuntu-24.04','--exec',lp(tool/'arm-linux-gnueabihf-readelf'),'-h','-A','-l','-d','-V',lp(binary)]);assert 'ELF32' in elf and 'VFP registers' in elf
    dataset=Path(trained['dataset']);manifest=json.loads((dataset/'manifest.json').read_text());fixtures=[]
    for record in manifest['records']:
        if record['split']!='test':continue
        with np.load(dataset/record['file'],allow_pickle=False) as z:frames=z['noisy'].reshape(8,1024).copy()
        for frame_index,x in enumerate(frames):
            name=f'test-{len(fixtures):03}';path=bundle/'inputs'/(name+'.iq');iq=np.column_stack((x.real,x.imag)).astype('<f4');path.write_bytes(iq.tobytes())
            f=features(x);logits=((f-mean)/scale)@w+b;prediction=int(np.argmax(logits));expected=np.concatenate((f,logits,[prediction]))
            actual=np.fromstring(run(name,[str(host),str(path)]).strip(),sep=',')
            np.testing.assert_allclose(actual[:14],f,rtol=1e-10,atol=1e-10);np.testing.assert_allclose(actual[14:17],logits,rtol=0,atol=1e-7);assert actual[17]==prediction
            fixtures.append({'name':name,'record_id':record['record_id'],'frame_index':frame_index,'nominal_snr_db':record['nominal_snr_db'],'truth':['BPSK','QPSK','16QAM'].index(record['modulation']),'expected':expected.tolist(),'input_sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    assert len(fixtures)==216
    (bundle/'expected.json').write_text(json.dumps(fixtures,indent=2)+'\n')
    script=['#!/bin/sh','set -eu','cd "$(dirname "$0")"','test ! -e outputs','sha256sum -c SHA256SUMS','mkdir outputs','uname -a > outputs/uname.txt']
    script += [f'./bin/baseline-infer inputs/{c["name"]}.iq > outputs/{c["name"]}.txt' for c in fixtures]
    script += ['./bin/baseline-infer inputs/test-000.iq --bench > outputs/benchmark.txt','echo ARM_FROZEN_BASELINE_DONE_SYNTHETIC_ONLY']
    (bundle/'run.sh').write_text('\n'.join(script)+'\n',newline='\n')
    (bundle/'SHA256SUMS').write_text('\n'.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.relative_to(bundle).as_posix() for p in sorted(bundle.rglob('*')) if p.is_file())+'\n',newline='\n')
    archive=out/(prefix+'.tar')
    with tarfile.open(archive,'w') as tar:
        for p in sorted(bundle.rglob('*')):
            if p.is_file():
                info=tar.gettarinfo(str(p),arcname=prefix+'/'+p.relative_to(bundle).as_posix());info.mode=0o755 if p.parent.name=='bin' else 0o644
                with p.open('rb') as f:tar.addfile(info,f)
    report={'status':'host_C_comparison_passed_ARM_pending','prefix':prefix,'archive':str(archive),'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'cases':216,'trained_model_sha256':trained['model_sha256'],'dataset_manifest_sha256':trained['dataset_manifest_sha256'],'feature_tolerance':{'absolute':1e-10,'relative':1e-10},'logit_absolute_tolerance':1e-7,'source':'SYNTHETIC_NOT_REAL_RF','quantization':'none_FP64','real_RF_accuracy':'not_measured'}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()
