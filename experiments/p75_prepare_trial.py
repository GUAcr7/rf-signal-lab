"""Freeze a new source seed and live-candidate acceptance before RF acquisition."""
import argparse,gzip,hashlib,io,tarfile
from datetime import datetime,timezone
from pathlib import Path
from p45_checkpoint import ROOT,read,write,sha,rel
from p46_restore_tx import validate_source_package
from p46_known_source import source_bytes_valid
from rfsig.tx_waveforms import make_tx_waveform,pack_tx_iq_le16


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--build',required=True,type=Path);a=ap.parse_args()
    b=read(a.build)
    if b['status']!='passed_P75_phase_candidate_build_lifecycle12_not_deployed':raise ValueError('P75 lifecycle build required')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p75-plan-%Y%m%dT%H%M%SZ');out.mkdir()
    seed=2026102601
    parent=ROOT/'results/p54-plan-20261024T042837Z/2026102315/report.json'
    validate_source_package(parent)
    directory=out/str(seed);directory.mkdir()
    files={k:(parent.parent/k).read_bytes() for k in ('guard','source.c')};references={}
    options=dict(sample_rate_hz=30720000,samples_per_symbol=128,symbol_count=1024,seed=seed,
                 offset_hz=960000,rolloff=.35,span_symbols=10)
    for name,mode in (('tone','tone'),('bpsk','BPSK'),('qpsk','QPSK'),('qam16','16QAM')):
        wave=make_tx_waveform(mode,digital_peak_counts=256,**options)
        raw=pack_tx_iq_le16(wave.iq);source_bytes_valid(raw)
        files[name]=raw;references[name]=wave.reference
    files['sums']=''.join(hashlib.sha256(v).hexdigest()+'  '+k+'\n' for k,v in files.items()).encode('ascii')
    stream=io.BytesIO()
    with tarfile.open(fileobj=stream,mode='w') as t:
        for name,value in files.items():
            item=tarfile.TarInfo(name);item.size=len(value);item.mode=0o755 if name=='guard' else 0o600
            t.addfile(item,io.BytesIO(value))
    for name,value in files.items():(directory/name).write_bytes(value)
    (directory/'pkg.gz').write_bytes(gzip.compress(stream.getvalue(),compresslevel=6,mtime=0))
    source=dict(status='host_peak256_source_package_prepared_not_uploaded',board_operations=False,
        guard_baseline_reproduced=True,source_peak_component_counts=256,
        files_sha256={name:sha(directory/name) for name in files},references=references,
        archive_sha256=sha(directory/'pkg.gz'),archive_bytes=(directory/'pkg.gz').stat().st_size,
        seed=seed,split='prospective_candidate_RF_validation',session_plan_only=True,real_RF_acquired=False)
    write(directory/'report.json',source);validate_source_package(directory/'report.json')
    protocol=dict(status='frozen_before_P75_RF_acquisition',created_utc=datetime.now(timezone.utc).isoformat(),
        build=rel(a.build),build_sha256=sha(a.build),binary_sha256=b['binary_sha256'],
        source=rel(directory/'report.json'),source_sha256=sha(directory/'report.json'),seed=seed,
        duration_ms=360000,UI_interval_ms=500,
        segments=[dict(phase=p,source=n,seconds=s) for p,n,s in
                  [('pilot','tone',15),('bpsk','bpsk',30),('qpsk','qpsk',30),('early','qam16',45),('late','qam16',45)]],
        late_minimum_calibration_age_s=180,stable_after_first_observation_s=2,stable_end_margin_s=3,
        minimum_observations_per_segment=5,minimum_coverage=.70,minimum_conditional_accuracy=.90,
        background_tone_stale_clipping_must_abstain=True,
        unchanged_RF=dict(TX_gain_db=-10,RX_manual_gain_db=0,peak_component_counts=256,
                          Fs_hz=30720000,LO_hz=2450000000,RF_BW_hz=18000000),
        snapshot_fixed_s=8,snapshot_limit=7,native_event_limit=12,archive_member_limit=72,archive_raw_max_bytes=16777216,
        weights_frozen=True,three_frame_unanimity=True,production_install=False,
        scope='prospectively frozen new-seed controlled real-RF regression; not general unknown-signal accuracy')
    write(out/'report.json',protocol);(out/'executed.py').write_bytes(Path(__file__).read_bytes())
    print(out)


if __name__=='__main__':main()
