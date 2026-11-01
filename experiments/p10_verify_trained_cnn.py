"""Verify each actual ARM trained CNN result against frozen Python reference."""
import argparse,hashlib,json,tarfile
from pathlib import Path,PurePosixPath
import numpy as np
from rfsig.trainable_cnn import preprocess,patches,forward
from rfsig.cnn_quantization import quantized_forward
from rfsig.modulation_baseline import confusion

def main():
    ap=argparse.ArgumentParser();ap.add_argument('prepared',type=Path);ap.add_argument('retrieved',type=Path);ap.add_argument('trained',type=Path);a=ap.parse_args()
    report=json.loads((a.prepared/'report.json').read_text());bundle=a.prepared/report['prefix'];cases=json.loads((bundle/'expected.json').read_text());transfer=json.loads((a.retrieved/'report.json').read_text(encoding='utf-8-sig'))
    assert not (a.retrieved/'outputs').exists() and not (a.retrieved/'verification.json').exists()
    archive=a.retrieved/'board-results.tar.gz';assert hashlib.sha256(archive.read_bytes()).hexdigest()==transfer['archive_sha256']
    assert hashlib.sha256((a.trained/'cnn-model.npz').read_bytes()).hexdigest()==report['frozen_model_sha256']
    assert hashlib.sha256((a.prepared/'fresh-holdout/manifest.json').read_bytes()).hexdigest()==report['fresh_holdout_manifest_sha256']
    for line in (bundle/'SHA256SUMS').read_text().splitlines():
        digest,name=line.split('  ',1);assert hashlib.sha256((bundle/name).read_bytes()).hexdigest()==digest
    with np.load(a.trained/'cnn-model.npz',allow_pickle=False) as z:model=dict(z)
    with np.load(a.prepared/'quantized-model.npz',allow_pickle=False) as z:q=dict(z)
    names={'outputs/'+c['name']+'-'+mode+'.txt' for c in cases for mode in ['fp32','int8']}|{'outputs/uname.txt','outputs/benchmark-fp32.txt','outputs/benchmark-int8.txt'};data={}
    with tarfile.open(archive,'r:gz') as tar:
        for m in tar:
            name=str(PurePosixPath(m.name))
            if m.isdir():assert name=='outputs';continue
            assert m.isfile() and name in names and name not in data and m.size<10000
            data[name]=tar.extractfile(m).read()
    assert set(data)==names and b'armv7l' in data['outputs/uname.txt']
    pred={'fp32':[],'int8':[]};errors={mode:[] for mode in pred};truth=[]
    for c in cases:
        raw=(bundle/'inputs'/(c['name']+'.iq')).read_bytes();assert hashlib.sha256(raw).hexdigest()==c['input_sha256'];iq=np.frombuffer(raw,dtype='<f4').reshape(1024,2);p=patches(preprocess((iq[:,0]+1j*iq[:,1])[None,:]))
        ref={'fp32':forward(p,model)[0],'int8':quantized_forward(p,q)[0]}
        for mode in pred:
            np.testing.assert_allclose(ref[mode],c[mode+'_logits'],rtol=0,atol=1e-12)
            actual=np.fromstring(data['outputs/'+c['name']+'-'+mode+'.txt'].decode().strip(),sep=',');assert actual.shape==(4,) and np.isfinite(actual).all()
            np.testing.assert_allclose(actual[:3],ref[mode],rtol=1e-4 if mode=='fp32' else 0,atol=5e-4 if mode=='fp32' else 1e-10)
            assert actual[3]==np.argmax(ref[mode]) and actual[3]==np.argmax(actual[:3]);pred[mode].append(int(actual[3]));errors[mode].append(float(max(abs(actual[:3]-ref[mode]))))
        truth.append(c['truth'])
    metrics={};performance={}
    for mode in pred:
        cm=confusion(truth,pred[mode]);assert cm.tolist()==report['evaluation'][mode]['confusion_rows_truth_cols_prediction']
        metrics[mode]={'accuracy':float(np.trace(cm)/cm.sum()),'confusion_rows_truth_cols_prediction':cm.tolist(),'maximum_logit_error':max(errors[mode]),'predictions_equal_Python':True}
        perf=json.loads(data['outputs/benchmark-'+mode+'.txt'].decode().splitlines()[1]);assert perf['mode']==mode and perf['repeats']==100 and 0<perf['p50_ms']<=perf['p95_ms']<=perf['max_ms'] and perf['maxrss_kib']>0;performance[mode]=perf
    (a.retrieved/'outputs').mkdir()
    for name,payload in data.items():(a.retrieved/name).write_bytes(payload)
    result={'status':'passed_trained_CNN_ARM_FP32_INT8_synthetic_holdout_only','cases':216,'independent_parent_records':27,'accuracy':metrics,'ARM_performance':performance,'quantization':report['calibration'],'model_sha256':report['frozen_model_sha256'],'holdout_manifest_sha256':report['fresh_holdout_manifest_sha256'],'real_RF_accuracy':'not_measured','live_RX':'not_connected','test_not_used_for_training_selection_or_calibration':True,'scope':'INT8 conv/dense MAC with INT32 accumulation; floating preprocessing and rescaling remain; not an integer-only neural runtime'}
    (a.retrieved/'verification.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
