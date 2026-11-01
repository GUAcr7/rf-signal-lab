"""Recover and independently verify software ARM spectra and new raw RX captures."""
import argparse,hashlib,json,tarfile
from pathlib import Path,PurePosixPath
import numpy as np
from p07b_prepare_arm_spectrum import verify

def main():
    ap=argparse.ArgumentParser();ap.add_argument('prepared',type=Path);ap.add_argument('retrieved',type=Path);a=ap.parse_args();r=json.loads((a.prepared/'report.json').read_text());b=a.prepared/r['prefix'];transfer=json.loads((a.retrieved/'report.json').read_text(encoding='utf-8-sig'));archive=a.retrieved/'board-results.tar.gz'
    assert hashlib.sha256(archive.read_bytes()).hexdigest()==transfer['archive_sha256'];assert not (a.retrieved/'outputs').exists()
    names={'outputs/'+c+suffix for c in r['known_cases'] for suffix in ['.json','.psd']}|{'outputs/uname.txt','outputs/run.txt'}
    for session in [1,2]:names|={f'outputs/session-{session}{suffix}' for suffix in ['.iq','.json','.before.txt','.after.txt']}|{f'outputs/rx-spectrum-{session}{suffix}' for suffix in ['.json','.psd']}
    data={}
    with tarfile.open(archive,'r:gz') as tar:
        for m in tar:
            name=str(PurePosixPath(m.name))
            if m.isdir():assert name=='outputs';continue
            assert m.isfile() and name in names and name not in data and m.size<1_000_000
            data[name]=tar.extractfile(m).read()
    assert set(data)==names and b'armv7l' in data['outputs/uname.txt'] and b'ARM_RX_CONTEXT_RELEASED status=0' in data['outputs/run.txt']
    out=a.retrieved/'outputs';out.mkdir()
    for name,payload in data.items():(a.retrieved/name).write_bytes(payload)
    checks=[{'name':c,**verify(b/'inputs'/(c+'.iq'),out/c)} for c in r['known_cases']];sessions=[]
    for session in [1,2]:
        prefix=out/f'session-{session}';raw=np.frombuffer(prefix.with_suffix('.iq').read_bytes(),dtype='<i2').reshape(-1,2).astype(np.int64);meta=json.loads(prefix.with_suffix('.json').read_text());bs=meta['block_samples'];assert len(raw)==bs*len(meta['blocks']) and meta['buffer_released'] and raw.min()>=-2048 and raw.max()<=2047
        hashes=[]
        for block in meta['blocks']:
            frame=raw[block['index']*bs:(block['index']+1)*bs];s=int(np.sum(frame**2,dtype=np.int64));assert block['sum_I2_Q2']==s and block['minimum']==int(frame.min()) and block['maximum']==int(frame.max());np.testing.assert_allclose(block['mean_I2_Q2'],s/bs,rtol=1e-11)
            hashes.append(hashlib.sha256(frame.astype('<i2').tobytes()).hexdigest())
        assert len(set(hashes))==len(hashes)
        for fmt in meta['format']:assert fmt['length']==16 and fmt['bits']==12 and fmt['shift']==0 and fmt['signed'] and not fmt['be'] and fmt['fully_defined'] and fmt['repeat']==1
        configs=[]
        for suffix in ['.before.txt','.after.txt']:
            cfg=dict(line.split('=',1) for line in prefix.with_suffix(suffix).read_text().splitlines());assert cfg['adc_sampling_frequency']==cfg['phy_sampling_frequency']=='30720000' and cfg['bist_prbs']==cfg['bist_tone']==cfg['loopback']=='0';configs.append(cfg)
        for key in configs[0]:
            if key!='hardwaregain':assert configs[0][key]==configs[1][key]
        spectrum=verify(prefix.with_suffix('.iq'),out/f'rx-spectrum-{session}');perf=spectrum['benchmark'];assert perf['repeats']==100 and 0<perf['p50_ms']<=perf['p95_ms']<=perf['max_ms']
        sessions.append({'session':session,'complex_samples':len(raw),'blocks':len(hashes),'unique_blocks':len(set(hashes)),'config_before':configs[0],'config_after':configs[1],**spectrum})
    result={'status':'passed_ARM_native_RX_then_software_FFT_PSD_ROI_snapshots','synthetic_reference_cases':checks,'new_RX_sessions':sessions,'new_RX_complex_samples':sum(s['complex_samples'] for s in sessions),'new_RX_spectrum_frames':sum(s['frames'] for s in sessions),'configuration_static_fields_unchanged':True,'hardware_gaps':'unknown','known_RF_target':'unknown','AI':'not_connected','FIR':'not_connected','FPGA_FFT':'not_implemented','real_RF_frequency_and_bandwidth_accuracy':'not_measured','PSD_units':'raw_counts_squared_per_Hz; not dBm','ordering':'capture finite sessions, release buffers, then process saved frames; not concurrent streaming'}
    (a.retrieved/'verification.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='synthetic_reference_cases'}))
if __name__=='__main__':main()
