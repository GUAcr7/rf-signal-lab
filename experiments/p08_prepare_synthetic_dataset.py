"""Create and independently verify synthetic-only balanced record splits."""
import hashlib,json,platform
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
from rfsig.synthetic_dataset import make_record,validate_records,CLASSES,SNR_DB,array_hash

def main():
    root=Path(__file__).resolve().parents[1]
    out=root/'data'/('p08-synthetic-v1-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    out.mkdir(parents=True);records=[]
    for modulation in CLASSES:
        for snr in SNR_DB:
            for index in range(20):
                r=make_record(modulation,snr,index);meta=r.metadata.copy()
                path=out/(meta['record_id']+'.npz')
                np.savez_compressed(path,clean=r.clean,noisy=r.noisy,bits=r.bits)
                with np.load(path,allow_pickle=False) as z:
                    for name in ['clean','noisy','bits']:assert array_hash(z[name])==meta[name+'_sha256']
                    noise=z['noisy'].astype(complex)-z['clean'].astype(complex)
                    measured=10*np.log10(np.mean(abs(z['clean'].astype(complex))**2)/np.mean(abs(noise)**2))
                    assert abs(measured-meta['measured_record_snr_db'])<1e-10 and abs(measured-snr)<.5
                meta['file']=path.name;meta['file_sha256']=hashlib.sha256(path.read_bytes()).hexdigest();records.append(meta)
    validation=validate_records(records)
    counts=Counter((r['modulation'],r['nominal_snr_db'],r['split']) for r in records)
    for c in CLASSES:
        for snr in SNR_DB:
            for split,n in [('train',14),('validation',3),('test',3)]:assert counts[c,snr,split]==n
    split_records={split:[r['record_id'] for r in records if r['split']==split] for split in ['train','validation','test']}
    (out/'split-manifest.json').write_text(json.dumps(split_records,indent=2)+'\n')
    manifest={'version':'synthetic-v1','source':'SYNTHETIC_NOT_REAL_RF','numpy':np.__version__,'python':platform.python_version(),'generator_sha256':hashlib.sha256((root/'src/rfsig/synthetic_dataset.py').read_bytes()).hexdigest(),'records':records}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    report={'status':'passed_synthetic_dataset_only','validation':validation,'record_split':{k:len(v) for k,v in split_records.items()},'frame_split':{k:len(v)*8 for k,v in split_records.items()},'class_frame_counts':{c:480 for c in CLASSES},'SNR_nominal_db':list(SNR_DB),'measured_SNR_range_db':[min(r['measured_record_snr_db'] for r in records),max(r['measured_record_snr_db'] for r in records)],'split_before_framing':True,'real_RF_records':0,'real_dataset_acceptance':'pending_known_label_RF_capture','model_training':'not_performed','quantization':'not_performed','manifest_sha256':hashlib.sha256((out/'manifest.json').read_bytes()).hexdigest(),'total_bytes':sum(p.stat().st_size for p in out.iterdir() if p.is_file())}
    (out/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'directory':str(out),'report':report}))

if __name__=='__main__':main()
