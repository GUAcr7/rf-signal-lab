"""Freeze trained real-RF weights/frontends and export matching x86/ARM inference."""
import argparse,json,subprocess
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
from p45_checkpoint import ROOT,read,write,sha,rel
from p36_build_rx_full import TOOL,posix
from p37_review_archives import archive_bytes,decode_rx12
from rfsig.trainable_cnn import preprocess,patches,forward
from rfsig.cnn_quantization import quantized_forward
from rfsig.rf_ai_calibration import adapt_calibrated
from rfsig.rf_ai_input import anti_alias_taps

def fmt(array,kind):
    a=np.asarray(array)
    if a.ndim==2:return '{'+','.join(fmt(row,kind) for row in a)+'}'
    if kind=='float':
        values=[format(float(v),'.9g') for v in a];values=[v+('.0' if '.' not in v and 'e' not in v else '')+'f' for v in values]
    elif kind=='int':values=[str(int(v)) for v in a]
    else:values=[format(float(v),'.17g') for v in a]
    return '{'+','.join(values)+'}'

def export_headers(folder,model,q,model_sha,provenance='REAL RF'):
    if not all(np.isfinite(v).all() for v in model.values()) or not np.array_equal(q['dense_b'],model['dense_b']):raise ValueError('inconsistent model')
    head=['/* Frozen '+provenance+' model '+model_sha+'; three controlled classes only. */']
    for name,a,ctype,kind in [('conv_weights',model['conv_w'],'float','float'),('conv_bias',model['conv_b'],'float','float'),('dense_weights',model['dense_w'],'float','float'),('dense_bias',model['dense_b'],'float','float'),('quant_conv_weights',q['conv_w'],'int8_t','int'),('quant_conv_bias',q['conv_b'],'int32_t','int'),('quant_dense_weights',q['dense_w'],'int8_t','int')]:
        head.append('static const '+ctype+' '+name+''.join('['+str(n)+']' for n in a.shape)+'='+fmt(a,kind)+';')
    for name,value in q.items():
        if 'scale' in name:head.append('static const double '+name+'='+format(float(value),'.17g')+';')
    (folder/'trained_model.h').write_text('\n'.join(head)+'\n',encoding='utf-8')
    (folder/'rf_frontend.h').write_text('/* Fixed P51 FIR; full-block guards and 16x decimation. */\nstatic const double rf_taps[513]='+fmt(anti_alias_taps(),'double')+';\n',encoding='utf-8')

def main():
    p=argparse.ArgumentParser();p.add_argument('--trained',required=True,type=Path);args=p.parse_args();trained=read(args.trained)
    if trained['status']!='trained_REAL_RF_validation_selected_test_not_acquired' or trained['test_real_frames']!=0:raise ValueError('test-unexposed real training required')
    model_path=args.trained.parent/'cnn-model.npz';q_path=args.trained.parent/'quantized-model.npz'
    if sha(model_path)!=trained['model_sha256'] or sha(q_path)!=trained['quantized_model_sha256']:raise ValueError('weights changed')
    with np.load(model_path,allow_pickle=False) as z:model=dict(z)
    with np.load(q_path,allow_pickle=False) as z:q=dict(z)
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p52-export-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False);bundle=out/'bundle';bundle.mkdir()
    export_headers(bundle,model,q,sha(model_path))
    template=ROOT/'embedded/tiny_cnn_probe/trained_cnn_infer.c';frontend=ROOT/'embedded/tiny_cnn_probe/real_rf_infer.c'
    (bundle/template.name).write_text(template.read_text().replace('Frozen synthetic-trained CNN.','Frozen REAL-RF-trained CNN.'),encoding='utf-8')
    (bundle/frontend.name).write_bytes(frontend.read_bytes())
    r=dict(status='building_real_RF_export',board_operations=False,AI_accepted=False,independent_test_accuracy='not_yet_measured',numeric_checks=[],stages=[])
    def save():write(out/'report.json',r)
    def run(label,args):
        child=subprocess.run([str(a) for a in args],capture_output=True,timeout=180)
        (out/(label+'.stdout')).write_bytes(child.stdout);(out/(label+'.stderr')).write_bytes(child.stderr)
        r['stages'].append(dict(label=label,exit_code=child.returncode));save()
        if child.returncode:raise ValueError(label+' failed')
        return child.stdout.decode()
    save()
    flags=['-std=c99','-O2','-Wall','-Wextra','-Werror','-fno-fast-math','-ffp-contract=off']
    try:
        host=out/'real-rf-host.exe';arm=out/'real-rf-arm'
        run('host-build',['C:/msys64/ucrt64/bin/gcc.exe',*flags,'-I',bundle,bundle/frontend.name,'-o',host,'-lm'])
        run('ARM-build',['wsl.exe','--exec',posix(TOOL/'arm-linux-gnueabihf-gcc'),*flags,'-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard','-marm','-I',posix(bundle),posix(bundle/frontend.name),'-o',posix(arm),'-lm','-lrt'])
        elf=run('ARM-ELF',['wsl.exe','--exec',posix(TOOL/'arm-linux-gnueabihf-readelf'),'-h','-A','-l','-V',posix(arm)])
        if 'ELF32' not in elf or 'VFP registers' not in elf or '/lib/ld-linux-armhf.so.3' not in elf:raise ValueError('ARM ABI differs')
        dataset=read(ROOT/trained['dataset']);batch=read(ROOT/dataset['batch'])
        validation=next(g for g in batch['groups'] if g['role']=='validation')
        calibration=next(v['calibration'] for v in dataset['calibrations'] if v['seed']==validation['seed'])
        archives=read(ROOT/validation['archives']);(out/'fixtures').mkdir()
        fixtures=[]
        for name in ('bpsk','qpsk','qam16'):
            entry=next(v for v in archives['cases'] if v['name']==name);path=Path(entry['report']);path=path if path.is_absolute() else ROOT/path
            _,raw=archive_bytes(path)
            for block in range(2):
                packed=raw[block*262144:(block+1)*262144];file=out/'fixtures'/f'{name}-{block}.bin';file.write_bytes(packed)
                pairs=decode_rx12(packed);iq=pairs[:,0].astype(float)+1j*pairs[:,1]
                frames,_=adapt_calibrated(iq,sample_rate_hz=30720000,calibration=calibration)
                tensor=patches(preprocess(np.asarray(frames,dtype=np.complex64)))
                refs=dict(fp32=forward(tensor,model),int8=quantized_forward(tensor,q))
                for mode,logits in refs.items():
                    label=name+'-'+str(block)+'-'+mode
                    text=run(label,[host,file,str(calibration['frequency_hz']),mode]);actual=np.array([np.fromstring(line,sep=',') for line in text.splitlines()])
                    if actual.shape!=(3,5):raise ValueError('C frame layout differs')
                    np.testing.assert_allclose(actual[:,1:4],logits,rtol=1e-4,atol=5e-4)
                    if not np.array_equal(actual[:,4].astype(int),np.argmax(logits,axis=1)):raise ValueError('C prediction differs')
                    r['numeric_checks'].append(dict(fixture=file.name,mode=mode,frames=3,max_logit_absolute_error=float(np.max(abs(actual[:,1:4]-logits))),same_prediction=True));save()
                fixtures.append(dict(path=rel(file),sha256=sha(file),mode=trained['selected_mode'],frequency_hz=calibration['frequency_hz'],seed=validation['seed'],source_name=name,block=block))
        # No test RX has been acquired or read at this point.
        paths=dict(model=model_path,quantized=q_path,trained=args.trained,plan=ROOT/trained['plan'],dataset=ROOT/trained['dataset'],host=host,ARM=arm,
            header=bundle/'trained_model.h',taps=bundle/'rf_frontend.h',C=bundle/template.name,frontend=bundle/frontend.name,
            frontend_source=frontend,adapter=ROOT/'src/rfsig/rf_ai_input.py',calibration=ROOT/'src/rfsig/rf_ai_calibration.py',
            preprocess=ROOT/'src/rfsig/trainable_cnn.py',quantization=ROOT/'src/rfsig/cnn_quantization.py',dataset_builder=ROOT/'experiments/p52_make_dataset.py',
            learning=ROOT/'src/rfsig/real_rf_learning.py',trainer=ROOT/'experiments/p52_train_real.py',exporter=Path(__file__),
            evaluator=ROOT/'experiments/p52_evaluate_real.py',ARM_verifier=ROOT/'experiments/p52_arm_verify.py',RAM_gate=ROOT/'experiments/p52_ram.py')
        r.update(status='frozen_real_RF_model_before_unseen_test_capture',frozen_utc=datetime.now(timezone.utc).isoformat(),
            frozen_inputs={key:dict(path=rel(path),sha256=sha(path)) for key,path in paths.items()},selected_mode=trained['selected_mode'],class_order=trained['class_order'],
            validation=trained['validation'],fixtures=fixtures,test_RF_acquired=False,
            C_full_frontend_and_Python_match=True,full_frontend='packed RX12/common IF/mix/513tap FIR/16x/3x1024/DC/RMS/CNN',
            labels_used_by_inference=False,live_AI_on_LCD=False)
    except Exception as e:r.update(status='failed_export_not_frozen',error=repr(e))
    save();print(out);print(r['status'])
    return 0 if r['status'].startswith('frozen_') else 1
if __name__=='__main__':raise SystemExit(main())
