"""Calibrate the common session IF using only the separately captured P46 tone."""
from datetime import datetime,timezone
from pathlib import Path
from p45_checkpoint import ROOT,read,write,sha,rel
from p37_review_archives import archive_bytes,decode_rx12
from rfsig.rf_ai_calibration import common_tone_calibration

def main():
    state=read(ROOT/'results/p46-active.json');paths={k:ROOT/state['reports'][k]['path'] for k in ('trial','archives')}
    if any(sha(p)!=state['reports'][k]['sha256'] for k,p in paths.items()):raise ValueError('P46 evidence changed')
    trial=read(paths['trial']);archives=read(paths['archives'])
    if archives['trial_sha256']!=sha(paths['trial']):raise ValueError('capture/archive mismatch')
    entry=next(v for v in archives['cases'] if v['name']=='tone');archive=Path(entry['report'])
    capture=next(v for v in trial['cases'] if v['name']=='tone')
    if sha(archive)!=entry['report_sha256']:raise ValueError('tone archive report changed')
    meta,raw=archive_bytes(archive);m=capture['native_metadata']
    if (meta['verified_raw_sha256']!=capture['raw_sha256'] or meta['expected_boot']!=trial['expected_boot']
        or m['frames_per_buffer']!=65536 or m['frame_bytes']!=4 or m['source_format']!='le:S12/16>>0'
        or m['channels']!=['voltage0:I','voltage1:Q'] or not m['scan_layout_validated']
        or len(raw)!=capture['blocks']*65536*4):raise ValueError('tone packed layout differs')
    pairs=decode_rx12(raw);iq=pairs[:,0].astype(float)+1j*pairs[:,1]
    calibration=common_tone_calibration(iq.reshape(capture['blocks'],65536))
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p51-tone-calibration-%Y%m%dT%H%M%SZ');out.mkdir()
    write(out/'report.json',dict(status='passed_tone_only_common_IF_calibration',calibration=calibration,
        inputs={k:dict(path=rel(p),sha256=sha(p)) for k,p in dict(paths,archive=archive).items()},
        source_sha256=sha(ROOT/'src/rfsig/rf_ai_calibration.py'),
        modulation_labels_used=False,modulation_samples_used=False,classifier_scores_used=False,
        board_operations=False,absolute_RF_frequency_calibrated=False))
    (out/'executed.py').write_bytes(Path(__file__).read_bytes());print(out);print(calibration['frequency_hz'])

if __name__=='__main__':main()
