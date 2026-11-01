"""Tone-only current-boot IF calibration from complete hash-checked archives."""
import argparse
from datetime import datetime,timezone
from pathlib import Path
from p45_checkpoint import ROOT,read,write,sha,rel
from p37_review_archives import archive_bytes,decode_rx12
from rfsig.rf_ai_calibration import common_tone_calibration

def main():
    p=argparse.ArgumentParser();p.add_argument('--archives',required=True,type=Path);args=p.parse_args()
    archives=read(args.archives);trial_path=Path(archives['trial']);trial=read(trial_path)
    if (archives['status']!='passed_all_known_source_raw_buffers_archived' or sha(trial_path)!=archives['trial_sha256']
        or trial['status']!='passed_bounded_known_source_captures_pending_host_archive' or not trial['all_TX_cleanup_verified']):raise ValueError('completed calibrated-tone capture required')
    if len(trial['cases'])!=1 or trial['cases'][0]['name']!='tone':raise ValueError('tone only; do not read modulation labels or scores')
    case=trial['cases'][0];entry=archives['cases'][0];archive_path=Path(entry['report'])
    if sha(archive_path)!=entry['report_sha256']:raise ValueError('raw archive changed')
    meta,raw=archive_bytes(archive_path);native=case['native_metadata']
    if (meta['expected_boot']!=trial['expected_boot'] or meta['verified_raw_sha256']!=case['raw_sha256']
        or native['channels']!=['voltage0:I','voltage1:Q'] or native['frame_bytes']!=4
        or not native['scan_layout_validated'] or len(raw)!=case['blocks']*262144):raise ValueError('tone RX1 layout/boot differs')
    pairs=decode_rx12(raw);x=pairs[:,0].astype(float)+1j*pairs[:,1]
    calibration=common_tone_calibration(x.reshape(case['blocks'],65536))
    source=Path(trial['source_report'])
    if sha(source)!=trial['source_report_sha256']:raise ValueError('source provenance changed')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p55-current-calibration-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    r=dict(status='passed_tone_only_common_IF_calibration',expected_boot=trial['expected_boot'],calibration=calibration,
        source_report=rel(source),source_report_sha256=sha(source),trial=rel(trial_path),trial_sha256=sha(trial_path),
        archives=rel(args.archives),archives_sha256=sha(args.archives),archive=rel(archive_path),archive_sha256=sha(archive_path),
        modulation_labels_used=False,modulation_samples_used=False,classifier_scores_used=False,
        board_operations=False,absolute_RF_frequency_calibrated=False)
    write(out/'report.json',r);(out/'executed.py').write_bytes(Path(__file__).read_bytes());print(out);print(r['status'])
if __name__=='__main__':main()
