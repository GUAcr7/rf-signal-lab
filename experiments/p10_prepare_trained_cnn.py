"""Calibrate only on training; generate fresh holdout after freezing; export C."""
import argparse,hashlib,json,tarfile,subprocess
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
from rfsig.synthetic_dataset import CLASSES,make_record,array_hash,validate_records
from rfsig.trainable_cnn import preprocess,patches,forward
from rfsig.cnn_quantization import calibrate,quantized_forward
from rfsig.modulation_baseline import confusion

def lp(path):s=path.resolve().as_posix();return '/mnt/'+s[0].lower()+s[2:]
def main():
    ap=argparse.ArgumentParser();ap.add_argument('trained',type=Path);a=ap.parse_args();root=Path(__file__).resolve().parents[1]
    frozen=json.loads((a.trained/'report.json').read_text());model_path=a.trained/'cnn-model.npz';assert hashlib.sha256(model_path.read_bytes()).hexdigest()==frozen['model_sha256']
    with np.load(model_path,allow_pickle=False) as z:model={k:z[k].copy() for k in z.files}
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');prefix='trained-cnn-'+stamp;out=root/'results'/('p10-trained-cnn-'+stamp);out.mkdir();bundle=out/prefix;(bundle/'inputs').mkdir(parents=True);(bundle/'bin').mkdir();holdout=out/'fresh-holdout';holdout.mkdir()
    dataset=Path(frozen['dataset']);old=json.loads((dataset/'manifest.json').read_text());assert hashlib.sha256((dataset/'manifest.json').read_bytes()).hexdigest()==frozen['dataset_manifest_sha256'];train=[]
    for r in old['records']:
        if r['split']=='train':
            f=dataset/r['file'];assert hashlib.sha256(f.read_bytes()).hexdigest()==r['file_sha256']
            with np.load(f,allow_pickle=False) as z:train.extend(z['noisy'].reshape(8,1024).copy())
    q=calibrate(patches(preprocess(np.array(train))),model);np.savez(out/'quantized-model.npz',**q)
    calibration={'source_split':'train','frames':1008,'activation_percentile':99.9,'rounding':'nearest ties to even','integer_MAC':'INT8 input/weights, INT32 conv and dense accumulation; FP64 activation rescale and logit dequantization; FP64 DC/RMS preprocessing','scales':{k:v for k,v in q.items() if 'scale' in k},'quantized_payload_bytes':sum(v.nbytes if isinstance(v,np.ndarray) else 8 for v in q.values()),'test_not_used_for_calibration':True}
    (out/'calibration.json').write_text(json.dumps(calibration,indent=2)+'\n')
    def fmt(array,kind):
        if array.ndim==2:return '{'+','.join(fmt(row,kind) for row in array)+'}'
        if kind=='float':vals=[format(float(v),'.9g') for v in array];vals=[v+('.0' if '.' not in v and 'e' not in v else '')+'f' for v in vals]
        elif kind=='int':vals=[str(int(v)) for v in array]
        else:vals=[format(float(v),'.17g') for v in array]
        return '{'+','.join(vals)+'}'
    head=['/* Frozen CNN SHA256 '+frozen['model_sha256']+'; synthetic data only. */']
    for name,arr,ctype,kind in [('conv_weights',model['conv_w'],'float','float'),('conv_bias',model['conv_b'],'float','float'),('dense_weights',model['dense_w'],'float','float'),('dense_bias',model['dense_b'],'float','float'),('quant_conv_weights',q['conv_w'],'int8_t','int'),('quant_conv_bias',q['conv_b'],'int32_t','int'),('quant_dense_weights',q['dense_w'],'int8_t','int')]:
        dims=''.join('['+str(n)+']' for n in arr.shape);head.append('static const '+ctype+' '+name+dims+'='+fmt(arr,kind)+';')
    for name,value in q.items():
        if 'scale' in name:head.append('static const double '+name+'='+format(value,'.17g')+';')
    (bundle/'trained_model.h').write_text('\n'.join(head)+'\n',newline='\n');source=root/'embedded/tiny_cnn_probe/trained_cnn_infer.c';(bundle/source.name).write_bytes(source.read_bytes())
    host=out/'trained-cnn-host.exe';binary=bundle/'bin/trained-cnn';flags=['-std=c99','-O2','-Wall','-Wextra','-Werror','-fno-fast-math','-ffp-contract=off']
    def run(name,cmd):
        r=subprocess.run(cmd,capture_output=True,timeout=180);(out/(name+'.stdout.txt')).write_bytes(r.stdout);(out/(name+'.stderr.txt')).write_bytes(r.stderr)
        if r.returncode:raise RuntimeError(name+': '+str(r.returncode))
        return r.stdout.decode()
    run('host-compile',['C:/msys64/ucrt64/bin/gcc.exe',*flags,'-I',str(bundle),str(source),'-o',str(host),'-lm'])
    tool=Path('E:/FPGA_Tools/ARM-GNU-A-8.3-2019.03/attempt-2/gcc-arm-8.3-2019.03-x86_64-arm-linux-gnueabihf/bin')
    run('arm-compile',['wsl.exe','-d','Ubuntu-24.04','--exec',lp(tool/'arm-linux-gnueabihf-gcc'),*flags,'-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard','-marm','-I',lp(bundle),lp(source),'-o',lp(binary),'-lm','-lrt'])
    elf=run('arm-elf',['wsl.exe','-d','Ubuntu-24.04','--exec',lp(tool/'arm-linux-gnueabihf-readelf'),'-h','-A','-l','-d','-V',lp(binary)]);assert 'ELF32' in elf and 'VFP registers' in elf
    # Generate independent final test only after frozen model and train-only calibration.
    records=[];fixtures=[];truth=[];snr=[];pf=[];pq=[];old_frames={h for r in old['records'] for h in r['frame_sha256']}
    for c in CLASSES:
        for s in [10,15,20]:
            for idx in [17,18,19]:
                r=make_record(c,s,idx,root_seed=20261012);meta=r.metadata.copy();meta['record_id']=meta['record_id'].replace('sim-v1','sim-holdout-seed20261012');meta['file']=meta['record_id']+'.npz'
                assert not old_frames.intersection(meta['frame_sha256'])
                file=holdout/meta['file'];np.savez_compressed(file,clean=r.clean,noisy=r.noisy,bits=r.bits);meta['file_sha256']=hashlib.sha256(file.read_bytes()).hexdigest();records.append(meta)
                for i,frame in enumerate(r.noisy.reshape(8,1024)):
                    name=f'test-{len(fixtures):03}';path=bundle/'inputs'/(name+'.iq');path.write_bytes(np.column_stack((frame.real,frame.imag)).astype('<f4').tobytes())
                    p=patches(preprocess(frame[None,:]));lf=forward(p,model)[0];lq=quantized_forward(p,q)[0]
                    for mode,ref in [('fp32',lf),('int8',lq)]:
                        actual=np.fromstring(run(name+'-'+mode,[str(host),str(path),mode]).strip(),sep=',');assert actual.shape==(4,) and np.isfinite(actual).all()
                        np.testing.assert_allclose(actual[:3],ref,rtol=1e-4 if mode=='fp32' else 0,atol=5e-4 if mode=='fp32' else 1e-10);assert actual[3]==np.argmax(ref)
                    fixtures.append({'name':name,'record_id':meta['record_id'],'frame_index':i,'nominal_snr_db':s,'truth':CLASSES.index(c),'fp32_logits':[float(v) for v in lf],'int8_logits':[float(v) for v in lq],'input_sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
                    truth.append(CLASSES.index(c));snr.append(s);pf.append(int(np.argmax(lf)));pq.append(int(np.argmax(lq)))
    assert validate_records(records)['records']==27
    (holdout/'manifest.json').write_text(json.dumps({'source':'SYNTHETIC_NOT_REAL_RF','root_seed':20261012,'frozen_model_sha256_before_generation':frozen['model_sha256'],'records':records},indent=2)+'\n')
    (bundle/'expected.json').write_text(json.dumps(fixtures,indent=2)+'\n');np.savez_compressed(out/'evaluation.npz',truth=truth,fp32_prediction=pf,int8_prediction=pq,nominal_snr=snr)
    def metrics(pred,selected=None):
        mask=np.ones(216,dtype=bool) if selected is None else np.array(snr)==selected;t=np.array(truth)[mask];pr=np.array(pred)[mask];cm=confusion(t,pr)
        return {'frames':len(t),'accuracy':float(np.mean(t==pr)),'per_class_accuracy':{c:float(cm[j,j]/cm[j].sum()) for j,c in enumerate(CLASSES)},'confusion_rows_truth_cols_prediction':cm.tolist()}
    script=['#!/bin/sh','set -eu','cd "$(dirname "$0")"','test ! -e outputs','sha256sum -c SHA256SUMS','mkdir outputs','uname -a > outputs/uname.txt']
    for f in fixtures:
        for mode in ['fp32','int8']:script.append(f'./bin/trained-cnn inputs/{f["name"]}.iq {mode} > outputs/{f["name"]}-{mode}.txt')
    for mode in ['fp32','int8']:script.append(f'./bin/trained-cnn inputs/test-000.iq {mode} --bench > outputs/benchmark-{mode}.txt')
    script.append('echo ARM_TRAINED_CNN_FP32_INT8_DONE_SYNTHETIC_ONLY');(bundle/'run.sh').write_text('\n'.join(script)+'\n',newline='\n')
    (bundle/'SHA256SUMS').write_text('\n'.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.relative_to(bundle).as_posix() for p in sorted(bundle.rglob('*')) if p.is_file())+'\n',newline='\n')
    archive=out/(prefix+'.tar')
    with tarfile.open(archive,'w') as tar:
        for p in sorted(bundle.rglob('*')):
            if p.is_file():
                info=tar.gettarinfo(str(p),arcname=prefix+'/'+p.relative_to(bundle).as_posix());info.mode=0o755 if p.parent.name=='bin' else 0o644
                with p.open('rb') as f:tar.addfile(info,f)
    report={'status':'fresh_holdout_host_C_passed_ARM_pending','prefix':prefix,'archive':str(archive),'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'cases':216,'independent_parent_records':27,'source':'SYNTHETIC_NOT_REAL_RF','frozen_model_sha256':frozen['model_sha256'],'fresh_holdout_manifest_sha256':hashlib.sha256((holdout/'manifest.json').read_bytes()).hexdigest(),'calibration':calibration,'evaluation':{'fp32':metrics(pf),'int8':metrics(pq)},'by_nominal_snr':{mode:{str(s):metrics(pred,s) for s in [10,15,20]} for mode,pred in [('fp32',pf),('int8',pq)]},'tolerance':{'fp32_abs':5e-4,'fp32_relative':1e-4,'int8_logits_abs':1e-10},'quantization_does_not_use_test':True,'real_RF_accuracy':'not_measured','live_RX':'not_connected','test_policy':'fresh seed after weight freezing; no retraining or retuning after this evaluation'}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()
