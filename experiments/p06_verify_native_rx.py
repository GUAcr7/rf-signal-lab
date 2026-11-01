"""Independently recompute actual ARM RX snapshots and compare saved settings."""
import argparse,hashlib,json,tarfile
from pathlib import Path,PurePosixPath
import numpy as np

def config(data):
    return dict(line.split('=',1) for line in data.decode().splitlines() if '=' in line)

def main():
    p=argparse.ArgumentParser();p.add_argument('retrieved',type=Path);a=p.parse_args()
    transfer=json.loads((a.retrieved/'report.json').read_text(encoding='utf-8-sig'))
    archive=a.retrieved/'board-results.tar.gz'
    assert hashlib.sha256(archive.read_bytes()).hexdigest()==transfer['archive_sha256']
    names={'outputs/run.txt','outputs/uname.txt'}
    for s in [1,2]:names.update(f'outputs/session-{s}.{ext}' for ext in ['iq','json','before.txt','after.txt'])
    data={}
    with tarfile.open(archive,'r:gz') as tar:
        for m in tar:
            name=str(PurePosixPath(m.name))
            if m.isdir():assert name=='outputs';continue
            assert m.isfile() and name in names and name not in data and m.size<150000
            data[name]=tar.extractfile(m).read()
    assert set(data)==names and b'ARM_RX_CONTEXT_RELEASED status=0' in data['outputs/run.txt']
    assert b'armv7l' in data['outputs/uname.txt']
    summaries=[];all_hashes=[]
    for s,block_samples,block_count in [(1,4096,8),(2,1024,4)]:
        raw=data[f'outputs/session-{s}.iq']
        iq=np.frombuffer(raw,dtype='<i2').reshape(block_count,block_samples,2)
        meta=json.loads(data[f'outputs/session-{s}.json'])
        assert meta['session']==s and meta['block_samples']==block_samples and len(meta['blocks'])==block_count
        assert meta['buffer_released'] and not meta['RF_writes'] and meta['hardware_gaps']=='unknown'
        for channel,f in enumerate(meta['format']):
            assert f['channel']==f'voltage{channel}' and f['length']==16 and f['signed'] and f['repeat']==1
        before=config(data[f'outputs/session-{s}.before.txt']);after=config(data[f'outputs/session-{s}.after.txt'])
        stable=set(before)-{'hardwaregain'}
        assert all(before[k]==after[k] for k in stable)
        for k in ['bist_prbs','bist_tone','loopback']:
            assert all(int(v)==0 for v in before[k].split())
        block_hashes=[]
        for block,record in zip(iq,meta['blocks']):
            wide=block.astype(np.int64);power_sum=int(np.sum(wide*wide));power=power_sum/block_samples
            assert record['refill_bytes']==block_samples*4 and power_sum==record['sum_I2_Q2']
            assert abs(power-record['mean_I2_Q2'])<=max(1e-8,abs(power)*1e-10)
            assert int(wide.min())==record['minimum'] and int(wide.max())==record['maximum']
            assert record['refill_ms']>=0 and record['host_done_s']>=record['host_start_s']
            digest=hashlib.sha256(block.tobytes()).hexdigest();block_hashes.append(digest);all_hashes.append(digest)
        assert len(set(block_hashes))==block_count
        assert np.unique(iq.reshape(-1,2),axis=0).shape[0]>100
        summaries.append({'session':s,'blocks':block_count,'complex_samples':block_count*block_samples,'format':meta['format'],'config_before':before,'config_after':after,'unique_block_hashes':len(set(block_hashes)),'block_hashes':block_hashes,'elapsed_s':meta['elapsed_s'],'refill_ms':[b['refill_ms'] for b in meta['blocks']],'maxrss_kib':meta['maxrss_kib'],'mean_power_range':[min(b['mean_I2_Q2'] for b in meta['blocks']),max(b['mean_I2_Q2'] for b in meta['blocks'])],'buffer_released':True})
    assert len(set(all_hashes))==12
    assert not (a.retrieved/'outputs').exists() and not (a.retrieved/'verification.json').exists()
    (a.retrieved/'outputs').mkdir()
    for name,payload in data.items():(a.retrieved/name).write_bytes(payload)
    report={'status':'passed_native_ARM_RX_snapshots_only','sessions':summaries,'complex_samples':36864,'independent_integer_statistics':'exact','configuration_static_fields_unchanged':True,'hardware_gaps':'unknown','RF_target':'unknown','live_model_integration':'pending','FIR_integration':'pending; exposed sample format must be adapted explicitly; 1MS/s FIR coefficients are not valid at 30.72MS/s','throughput':'only bounded snapshot timings; not sustained lossless reception'}
    (a.retrieved/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))

if __name__=='__main__':main()
