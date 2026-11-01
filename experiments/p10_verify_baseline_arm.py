"""Independently check frozen-model ARM outputs and sealed synthetic test metrics."""
import argparse,hashlib,json,tarfile
from pathlib import Path,PurePosixPath
import numpy as np
from rfsig.modulation_baseline import features,confusion

def main():
    p=argparse.ArgumentParser();p.add_argument('prepared',type=Path);p.add_argument('retrieved',type=Path);a=p.parse_args()
    prepared=json.loads((a.prepared/'report.json').read_text());transfer=json.loads((a.retrieved/'report.json').read_text(encoding='utf-8-sig'))
    bundle=a.prepared/prepared['prefix'];expected=json.loads((bundle/'expected.json').read_text())
    assert not (a.retrieved/'outputs').exists() and not (a.retrieved/'verification.json').exists()
    for line in (bundle/'SHA256SUMS').read_text().splitlines():
        digest,name=line.split('  ',1);assert hashlib.sha256((bundle/name).read_bytes()).hexdigest()==digest
    archive=a.retrieved/'board-results.tar.gz';assert hashlib.sha256(archive.read_bytes()).hexdigest()==transfer['archive_sha256']
    names={'outputs/'+c['name']+'.txt' for c in expected}|{'outputs/uname.txt','outputs/benchmark.txt'};data={}
    with tarfile.open(archive,'r:gz') as tar:
        for m in tar:
            name=str(PurePosixPath(m.name))
            if m.isdir():assert name=='outputs';continue
            assert m.isfile() and name in names and name not in data and m.size<10000
            data[name]=tar.extractfile(m).read()
    assert set(data)==names and b'armv7l' in data['outputs/uname.txt']
    errors=[];truth=[];prediction=[]
    for c in expected:
        iq=np.frombuffer((bundle/'inputs'/(c['name']+'.iq')).read_bytes(),dtype='<f4').reshape(1024,2)
        independent=features(iq[:,0]+1j*iq[:,1]);reference=np.array(c['expected'])
        np.testing.assert_allclose(reference[:14],independent,rtol=1e-10,atol=1e-10)
        actual=np.fromstring(data['outputs/'+c['name']+'.txt'].decode().strip(),sep=',')
        assert actual.shape==(18,) and np.isfinite(actual).all()
        np.testing.assert_allclose(actual[:14],independent,rtol=1e-10,atol=1e-10)
        np.testing.assert_allclose(actual[14:17],reference[14:17],rtol=0,atol=1e-7)
        assert actual[17]==reference[17] and actual[17]==np.argmax(actual[14:17])
        truth.append(c['truth']);prediction.append(int(actual[17]));errors.append({'name':c['name'],'features_max_error':float(max(abs(actual[:14]-independent))),'logits_max_error':float(max(abs(actual[14:17]-reference[14:17])))})
    perf=json.loads(data['outputs/benchmark.txt'].decode().splitlines()[1]);assert perf['repeats']==100 and 0<perf['p50_ms']<=perf['p95_ms']<=perf['max_ms'] and perf['maxrss_kib']>0
    m=confusion(truth,prediction);assert m.tolist()==[[71,0,1],[0,72,0],[0,0,72]]
    (a.retrieved/'outputs').mkdir()
    for name,payload in data.items():(a.retrieved/name).write_bytes(payload)
    report={'status':'passed_frozen_traditional_baseline_ARM_synthetic_only','cases':216,'independent_parent_records':len(set(c['record_id'] for c in expected)),'predictions_equal_desktop':True,'feature_max_error':max(c['features_max_error'] for c in errors),'logits_max_error':max(c['logits_max_error'] for c in errors),'accuracy':float(np.trace(m)/m.sum()),'confusion_rows_truth_cols_prediction':m.tolist(),'benchmark':perf,'source':'SYNTHETIC_NOT_REAL_RF','quantization':'none_FP64','real_RF_accuracy':'not_measured','live_RX_integration':'not_connected','trained_model_sha256':prepared['trained_model_sha256'],'case_errors':errors}
    (a.retrieved/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='case_errors'}))
if __name__=='__main__':main()
