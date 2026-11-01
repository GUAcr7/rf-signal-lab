"""Check C RF frontend arithmetic using OLD weights; no classification acceptance."""
import argparse,json,subprocess,shutil
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
from p45_checkpoint import ROOT,read,write,sha,rel
from p52_export_real import export_headers
from p37_review_archives import archive_bytes,decode_rx12
from p36_build_rx_full import TOOL,posix
from rfsig.rf_ai_calibration import common_tone_calibration,adapt_calibrated
from rfsig.trainable_cnn import preprocess,patches,forward
from rfsig.cnn_quantization import quantized_forward

def main():
    p=argparse.ArgumentParser();p.add_argument('--archives',required=True,type=Path);args=p.parse_args()
    archives=read(args.archives)
    if archives['status']!='passed_all_known_source_raw_buffers_archived':raise ValueError('complete raw archive required')
    def raw(name):
        entry=next(v for v in archives['cases'] if v['name']==name);path=Path(entry['report']);return archive_bytes(path)[1]
    with np.load(ROOT/'results/p09-trained-cnn-20261011T055334Z/cnn-model.npz',allow_pickle=False) as z:model=dict(z)
    with np.load(ROOT/'results/p10-trained-cnn-20261011T055826Z/quantized-model.npz',allow_pickle=False) as z:q=dict(z)
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p52-frontend-probe-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False);bundle=out/'bundle';bundle.mkdir()
    export_headers(bundle,model,q,sha(ROOT/'results/p09-trained-cnn-20261011T055334Z/cnn-model.npz'),provenance='NUMERIC PROBE OLD SYNTHETIC')
    for name in ('trained_cnn_infer.c','real_rf_infer.c'):shutil.copy2(ROOT/'embedded/tiny_cnn_probe'/name,bundle/name)
    flags=['-std=c99','-O2','-Wall','-Wextra','-Werror','-fno-fast-math','-ffp-contract=off']
    r=dict(status='checking_numeric_frontend_only',old_weights_for_arithmetic_test=True,ML_training=False,AI_accepted=False,board_operations=False,checks=[])
    def run(label,cmd,expected=0):
        child=subprocess.run([str(v) for v in cmd],capture_output=True,timeout=90)
        (out/(label+'.stdout')).write_bytes(child.stdout);(out/(label+'.stderr')).write_bytes(child.stderr)
        if child.returncode!=expected:raise ValueError(label+' returned '+str(child.returncode))
        return child.stdout.decode()
    try:
        host=out/'rf-host.exe';arm=out/'rf-arm'
        run('host-build',['C:/msys64/ucrt64/bin/gcc.exe',*flags,'-I',bundle,bundle/'real_rf_infer.c','-o',host,'-lm'])
        run('ARM-build',['wsl.exe','--exec',posix(TOOL/'arm-linux-gnueabihf-gcc'),*flags,'-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard','-marm','-I',posix(bundle),posix(bundle/'real_rf_infer.c'),'-o',posix(arm),'-lm','-lrt'])
        pairs=decode_rx12(raw('tone'));x=pairs[:,0].astype(float)+1j*pairs[:,1];cal=common_tone_calibration(x.reshape(-1,65536))
        for name in ('bpsk','qpsk','qam16'):
            b=raw(name)[:262144];file=out/(name+'.bin');file.write_bytes(b);pairs=decode_rx12(b);x=pairs[:,0].astype(float)+1j*pairs[:,1]
            frames,_=adapt_calibrated(x,sample_rate_hz=30720000,calibration=cal);tensor=patches(preprocess(np.asarray(frames,dtype=np.complex64)))
            for mode,reference in [('fp32',forward(tensor,model)),('int8',quantized_forward(tensor,q))]:
                text=run(name+'-'+mode,[host,file,str(cal['frequency_hz']),mode]);a=np.array([np.fromstring(line,sep=',') for line in text.splitlines()])
                np.testing.assert_allclose(a[:,1:4],reference,rtol=1e-4,atol=5e-4)
                if not np.array_equal(a[:,4],np.argmax(reference,1)):raise ValueError('numeric class parity failed')
                r['checks'].append(dict(source=name,mode=mode,matched=True,max_logit_error=float(np.max(abs(a[:,1:4]-reference)))))
        file=out/'bpsk.bin';padding=out/'padding.bin';padding.write_bytes((np.frombuffer(file.read_bytes(),dtype='<u2')^0xf000).astype('<u2').tobytes())
        original=run('padding-reference',[host,file,str(cal['frequency_hz']),'int8'])
        if run('padding-undefined-high-bits',[host,padding,str(cal['frequency_hz']),'int8'])!=original:raise ValueError('undefined padding affected results')
        empty=out/'empty.bin';empty.write_bytes(b'')
        for label,f,frequency,mode in [('empty',empty,'960000','fp32'),('NaN',file,'NaN','fp32'),('badIF',file,'100000','fp32'),('no-label-hint',file,'960000','BPSK')]:
            run('reject-'+label,[host,f,frequency,mode],expected=2)
        r.update(status='passed_full_C_frontend_Python_parity_ARM_build_and_input_rejections_old_weights_only',padding_bits_ignored=True,input_rejections=4,real_AI_accuracy='not_evaluated')
    except Exception as e:r.update(status='failed_frontend_probe',error=repr(e))
    write(out/'report.json',r);print(out);print(r['status'])
    return 0 if r['status'].startswith('passed_') else 1
if __name__=='__main__':raise SystemExit(main())
