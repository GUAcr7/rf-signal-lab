"""Build grouped real RF AI frames from complete checked archives; no board access."""
import argparse,json,hashlib
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
from p45_checkpoint import ROOT,read,write,sha,rel
from p37_review_archives import archive_bytes,decode_rx12
from rfsig.rf_ai_calibration import common_tone_calibration,adapt_calibrated
from rfsig.real_rf_learning import validate_frame_groups
NAMES=('bpsk','qpsk','qam16')

def frames_from_batch(path,*,allowed_roles):
    batch=read(path)
    if batch['status']!='passed_all_planned_REAL_RF_groups_archived_and_quality_checked' or not set(batch['roles'])<=set(allowed_roles):raise ValueError('completed role-specific RF batch required')
    frames=[];rows=[];calibrations=[]
    for group in batch['groups']:
        if group['status']!='all_buffers_archived_and_known_source_quality_passed':raise ValueError('group failed quality')
        for key in ('trial','archives','quality'):
            if sha(ROOT/group[key])!=group[key+'_sha256']:raise ValueError('group evidence changed')
        trial=read(ROOT/group['trial']);archives=read(ROOT/group['archives'])
        if archives['trial_sha256']!=sha(ROOT/group['trial']):raise ValueError('mixed raw evidence')
        decoded={}
        for entry in archives['cases']:
            archive=ROOT/entry['report'] if not Path(entry['report']).is_absolute() else Path(entry['report'])
            if sha(archive)!=entry['report_sha256']:raise ValueError('archive changed')
            meta,raw=archive_bytes(archive);capture=next(v for v in trial['cases'] if v['name']==entry['name'])
            native=capture['native_metadata']
            if (meta['expected_boot']!=batch['expected_boot'] or meta['verified_raw_sha256']!=capture['raw_sha256']
                or native['channels']!=['voltage0:I','voltage1:Q'] or native['frame_bytes']!=4
                or not native['scan_layout_validated'] or len(raw)!=capture['blocks']*65536*4):raise ValueError('invalid RX1 packing/boundaries')
            packed=decode_rx12(raw);x=packed[:,0].astype(float)+1j*packed[:,1]
            decoded[entry['name']]=x.reshape(capture['blocks'],65536)
        calibration=common_tone_calibration(decoded['tone']);calibrations.append(dict(seed=group['seed'],calibration=calibration))
        # Model inputs depend only on raw IQ/common calibration, never the modulation label.
        for name in NAMES:
            for block,x in enumerate(decoded[name]):
                adapted,details=adapt_calibrated(x,sample_rate_hz=30720000,calibration=calibration)
                for index,frame in enumerate(adapted):
                    data=np.asarray(frame,dtype='<c8');digest=hashlib.sha256(data.tobytes()).hexdigest()
                    frames.append(data);rows.append(dict(seed=group['seed'],session=group['capture_session'],split=group['role'],
                        label=NAMES.index(name),source_name=name,block=block,frame=index,sha256=digest,
                        parent_trial=group['trial'],parent_archives=group['archives'],raw_start_input_center=details['frame_first_input_center'][index]))
    validate_frame_groups(rows)
    return np.asarray(frames),rows,calibrations

def main():
    p=argparse.ArgumentParser();p.add_argument('--batch',required=True,type=Path);args=p.parse_args()
    frames,rows,calibration=frames_from_batch(args.batch,allowed_roles=('train','validation'))
    for role,seeds in [('train',6),('validation',3)]:
        selected=[r for r in rows if r['split']==role]
        if len({r['seed'] for r in selected})!=seeds or len(selected)!=seeds*18:raise ValueError('all planned training/validation groups required')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p52-dataset-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    np.savez_compressed(out/'frames.npz',frames=frames,labels=np.array([v['label'] for v in rows]),split=np.array([v['split'] for v in rows]),seed=np.array([v['seed'] for v in rows]))
    report=dict(status='passed_grouped_REAL_RF_training_validation_dataset_test_not_acquired',batch=rel(args.batch),batch_sha256=sha(args.batch),
        frame_file_sha256=sha(out/'frames.npz'),class_order=['BPSK','QPSK','16QAM'],frame_records=rows,calibrations=calibration,
        real_frames=len(rows),training_frames=108,validation_frames=54,test_frames=0,
        split_unit='seed and capture session',old_P46_frames_included=False,frame_random_split=False,board_operations=False,
        frame_index_not_independent_RF_trials=True,measured_SNR_db=None)
    write(out/'report.json',report);print(out);print(report['status'])
if __name__=='__main__':main()
