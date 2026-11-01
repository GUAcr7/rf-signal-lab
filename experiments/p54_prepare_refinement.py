"""Validation-only longer training protocol with fresh, never-seen RF holdout.

P52 baseline and its already-running test remain immutable and separate.
"""
from datetime import datetime,timezone
from pathlib import Path
import copy,gzip,hashlib,io,tarfile
import numpy as np
from p45_checkpoint import ROOT,read,write,sha,rel
from p46_known_source import source_bytes_valid
from p46_restore_tx import validate_source_package
from p51_prepare_rf_bank import validate_splits
from rfsig.tx_waveforms import make_tx_waveform,pack_tx_iq_le16

def main():
    old_plan_path=ROOT/'results/p52-plan-20261024T032533Z/report.json';plan=copy.deepcopy(read(old_plan_path))
    dataset_path=ROOT/'results/p52-dataset-20261024T042524Z/report.json';dataset=copy.deepcopy(read(dataset_path))
    baseline=ROOT/'results/p52-trained-20261024T042525Z/report.json'
    # Decision uses validation results only. Baseline test archives/logits are
    # deliberately not loaded; seed2310..2312 will never evaluate this model.
    if read(baseline)['validation']['int8']['fraction_correct']>=.9:raise ValueError('refinement trigger absent')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p54-plan-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    parent=ROOT/plan['groups'][0]['package'];meta,_,_=validate_source_package(parent)
    groups=plan['groups'][:9];rng=np.random.default_rng(2026102402)
    for index,seed in enumerate((2026102313,2026102314,2026102315)):
        directory=out/str(seed);directory.mkdir()
        files={k:(parent.parent/k).read_bytes() for k in ('guard','source.c')};references={}
        options=dict(sample_rate_hz=30720000,samples_per_symbol=128,symbol_count=1024,seed=seed,offset_hz=960000,rolloff=.35,span_symbols=10)
        for name,mode in (('tone','tone'),('bpsk','BPSK'),('qpsk','QPSK'),('qam16','16QAM')):
            wave=make_tx_waveform(mode,digital_peak_counts=256,**options);raw=pack_tx_iq_le16(wave.iq);source_bytes_valid(raw)
            files[name]=raw;references[name]=wave.reference
        files['sums']=''.join(hashlib.sha256(value).hexdigest()+'  '+name+'\n' for name,value in files.items()).encode('ascii')
        stream=io.BytesIO()
        with tarfile.open(fileobj=stream,mode='w') as t:
            for name,value in files.items():
                entry=tarfile.TarInfo(name);entry.size=len(value);entry.mode=0o755 if name=='guard' else 0o600;t.addfile(entry,io.BytesIO(value))
        (directory/'pkg.gz').write_bytes(gzip.compress(stream.getvalue(),compresslevel=6,mtime=0))
        for name,value in files.items():(directory/name).write_bytes(value)
        report=dict(status='host_peak256_source_package_prepared_not_uploaded',board_operations=False,guard_baseline_reproduced=True,
            source_peak_component_counts=256,files_sha256={name:sha(directory/name) for name in files},references=references,
            archive_sha256=sha(directory/'pkg.gz'),archive_bytes=(directory/'pkg.gz').stat().st_size,seed=seed,split='test',session_plan_only=True,real_RF_acquired=False)
        write(directory/'report.json',report);validate_source_package(directory/'report.json')
        groups.append(dict(seed=seed,role='test',group_id='controlled-source-'+str(seed),planned_capture_session='p54-test-session-'+str(index+1),
            real_RF_acquired=False,package=rel(directory/'report.json'),package_sha256=sha(directory/'report.json'),
            case_order=['tone',*rng.permutation(['bpsk','qpsk','qam16']).tolist()]))
    validate_splits(groups)
    plan.update(groups=groups,additional_PC_only_holdout_source_packages=[g['package'] for g in groups if g['role']=='test'],
        protocol_frozen_utc=datetime.now(timezone.utc).isoformat(),baseline_plan=rel(old_plan_path),baseline_plan_sha256=sha(old_plan_path),
        baseline_validation=rel(baseline),baseline_validation_sha256=sha(baseline),
        refinement='3000 rather than 300 epochs; architecture, augmentation, optimizer, quantization and gates unchanged',
        existing_training_validation_dataset=rel(dataset_path),existing_training_validation_dataset_sha256=sha(dataset_path),
        baseline_test_seeds_excluded=[2026102310,2026102311,2026102312],baseline_test_inputs_or_results_read=False,
        scope='same controlled conditions; longer training selected by validation only; brand-new RF holdout required')
    plan['training']['epochs']=3000
    write(out/'report.json',plan);(out/'executed.py').write_bytes(Path(__file__).read_bytes())
    new_dataset=out/'dataset';new_dataset.mkdir();(new_dataset/'frames.npz').write_bytes((dataset_path.parent/'frames.npz').read_bytes())
    dataset.update(parent_dataset=rel(dataset_path),parent_dataset_sha256=sha(dataset_path),new_protocol=rel(out/'report.json'),
        new_holdout_seeds=[2026102313,2026102314,2026102315],baseline_test_data_included=False,test_frames=0)
    write(new_dataset/'report.json',dataset);print(out);print(new_dataset)
if __name__=='__main__':main()
