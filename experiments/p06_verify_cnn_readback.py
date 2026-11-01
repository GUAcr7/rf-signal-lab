"""Verify an untrained ARM operator probe, not classification accuracy."""
import argparse,hashlib,json,tarfile
from pathlib import Path,PurePosixPath
import numpy as np
from rfsig.tiny_cnn_probe import infer_counts

def main():
    p=argparse.ArgumentParser();p.add_argument('prepared',type=Path);p.add_argument('retrieved',type=Path);a=p.parse_args()
    prepared=json.loads((a.prepared/'report.json').read_text())
    transfer=json.loads((a.retrieved/'report.json').read_text(encoding='utf-8-sig'))
    out=a.retrieved/'verification.json'
    assert not out.exists() and not (a.retrieved/'outputs').exists()
    archive=a.retrieved/'board-results.tar.gz'
    assert hashlib.sha256(archive.read_bytes()).hexdigest()==transfer['archive_sha256']
    names={'outputs/'+c['name']+'.txt' for c in prepared['cases']}
    names.update({'outputs/uname.txt','outputs/benchmark.txt','outputs/benchmark-retry.txt'})
    data={}
    with tarfile.open(archive,'r:gz') as tar:
        for m in tar:
            name=str(PurePosixPath(m.name))
            if m.isdir(): assert name=='outputs'; continue
            assert m.isfile() and name in names and name not in data and m.size<10000
            data[name]=tar.extractfile(m).read()
    assert set(data)==names and data['outputs/benchmark.txt']==b''
    assert b'armv7l' in data['outputs/uname.txt']
    errors=[]
    for c in prepared['cases']:
        path=a.prepared/prepared['prefix']/'inputs'/(c['name']+'.iq')
        assert hashlib.sha256(path.read_bytes()).hexdigest()==c['sha256']
        expected=infer_counts(np.frombuffer(path.read_bytes(),dtype='<i2').reshape(1024,2))
        actual=np.fromstring(data['outputs/'+c['name']+'.txt'].decode(),sep=',')
        assert actual.shape==(3,) and np.isfinite(actual).all()
        np.testing.assert_allclose(actual,expected,rtol=0,atol=prepared['absolute_tolerance'])
        errors.append({'case':c['name'],'max_absolute_error':float(np.max(np.abs(actual-expected)))})
    lines=data['outputs/benchmark-retry.txt'].decode().splitlines()
    perf=json.loads(lines[1]);assert perf['untrained_operator_probe'] and perf['repeats']==300
    assert 0<perf['p50_ms']<=perf['p95_ms']<=perf['max_ms'] and perf['maxrss_kib']>0
    (a.retrieved/'outputs').mkdir()
    for name,payload in data.items():(a.retrieved/name).write_bytes(payload)
    report={'status':'passed_operator_probe_only','cases':errors,'benchmark':perf,'max_absolute_error':max(e['max_absolute_error'] for e in errors),'untrained':True,'accuracy':'not_measured','SNR':'not_applicable','dataset_split':'not_training_data','quantization':'not_performed','live_RX':'not_connected','known_failure':'original run.sh benchmark referenced nonexistent qpsk_shaped.iq; original empty file retained; separate corrected qpsk benchmark passed'}
    out.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'cases':len(errors),'max_error':report['max_absolute_error'],'benchmark':perf,'report':str(out.resolve())}))

if __name__=='__main__':main()
