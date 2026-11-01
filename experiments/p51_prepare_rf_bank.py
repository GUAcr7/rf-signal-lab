"""PC-only independently seeded controlled-source packages; no RF data acquired."""
from datetime import datetime,timezone
from pathlib import Path
import gzip,io,tarfile
from p45_checkpoint import ROOT,read,write,sha,rel
from p46_known_source import GUARD_SHA,source_bytes_valid
from p46_restore_tx import validate_source_package
from rfsig.tx_waveforms import make_tx_waveform,pack_tx_iq_le16

ROLES=('train',)*6+('validation',)*3+('test',)*3
SEEDS=tuple(2026102301+i for i in range(12))


def records():
    return [dict(seed=seed,role=role,group_id=f'controlled-source-{seed}',
        planned_capture_session=role+'-session-'+str(i//2+1 if role=='train' else i-(6 if role=='validation' else 9)+1),
        real_RF_acquired=False) for i,(seed,role) in enumerate(zip(SEEDS,ROLES))]


def validate_splits(rows):
    if len(rows)!=12 or len({r['seed'] for r in rows})!=12 or len({r['group_id'] for r in rows})!=12:
        raise ValueError('each independent seed/group belongs to exactly one split')
    for role,count in (('train',6),('validation',3),('test',3)):
        selected=[r for r in rows if r['role']==role]
        if len(selected)!=count or len({r['planned_capture_session'] for r in selected})!=3:
            raise ValueError('balanced seeds and three planned sessions per split required')
    groups={role:{r['planned_capture_session'] for r in rows if r['role']==role} for role in ('train','validation','test')}
    if any(groups[a]&groups[b] for a,b in (('train','validation'),('train','test'),('validation','test'))):
        raise ValueError('capture sessions must not cross splits')
    if any(r['seed']==20261016 or r['real_RF_acquired'] for r in rows):raise ValueError('old diagnostic source or false acquisition claim')


def main():
    rows=records();validate_splits(rows)
    parent=ROOT/'results/p46-source-20261022T121954Z/report.json';baseline,_,_=validate_source_package(parent)
    if baseline['files_sha256']['guard']!=GUARD_SHA:raise ValueError('guard changed')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p51-rf-bank-%Y%m%dT%H%M%SZ');out.mkdir()
    report=dict(status='preparing_PC_only',source_parent=rel(parent),source_parent_sha256=sha(parent),groups=rows,
        board_operations=False,RF_operations=False,real_RF_samples=0,ML_training_performed=False,
        independent_real_RF_accuracy='not_measured',source_seed_disjoint_from_P46=True,
        conditions=dict(Fs_hz=30720000,samples_per_symbol=128,symbol_rate_hz=240000,offset_hz=960000,
            component_DAC_peak=256,TX_hardwaregain_db=-10,RX_hardwaregain_db=0,RF_LO_hz=2450000000),
        evaluation_scope='single controlled IF/symbol-rate/gain condition; no measured SNR claim',
        test_policy='test RF capture only after model/preprocessing frozen; all windows from a seed/session stay in one split',
        frame_random_split_allowed=False,samples_are_TX_waveforms_not_RX_training_data=True)
    (out/'executed.py').write_bytes(Path(__file__).read_bytes());write(out/'report.json',report)
    for row in rows:
        directory=out/str(row['seed']);directory.mkdir()
        files={k:(parent.parent/k).read_bytes() for k in ('guard','source.c')};references={}
        options=dict(sample_rate_hz=30720000,samples_per_symbol=128,symbol_count=1024,seed=row['seed'],
            offset_hz=960000,rolloff=.35,span_symbols=10)
        for name,mode in (('tone','tone'),('bpsk','BPSK'),('qpsk','QPSK'),('qam16','16QAM')):
            wave=make_tx_waveform(mode,digital_peak_counts=256,**options);raw=pack_tx_iq_le16(wave.iq)
            source_bytes_valid(raw);files[name]=raw;references[name]=wave.reference
        files['sums']=''.join(__import__('hashlib').sha256(v).hexdigest()+'  '+k+'\n' for k,v in files.items()).encode('ascii')
        stream=io.BytesIO()
        with tarfile.open(fileobj=stream,mode='w') as archive:
            for name,raw in files.items():
                member=tarfile.TarInfo(name);member.size=len(raw);member.mode=0o755 if name=='guard' else 0o600
                archive.addfile(member,io.BytesIO(raw))
        payload=gzip.compress(stream.getvalue(),compresslevel=6,mtime=0);(directory/'pkg.gz').write_bytes(payload)
        for name,raw in files.items():(directory/name).write_bytes(raw)
        package=dict(status='host_peak256_source_package_prepared_not_uploaded',board_operations=False,
            guard_baseline_reproduced=True,guard_reproduced_only_waveform_seeds_intentionally_new=True,
            source_peak_component_counts=256,files_sha256={k:sha(directory/k) for k in files},references=references,
            archive_sha256=sha(directory/'pkg.gz'),archive_bytes=len(payload),seed=row['seed'],split=row['role'],
            session_plan_only=True,real_RF_acquired=False)
        write(directory/'report.json',package);validate_source_package(directory/'report.json')
        row.update(package=rel(directory/'report.json'),package_sha256=sha(directory/'report.json'))
    report.update(status='passed_12_seed_36_modulation_source_packages_PC_only_not_RF_data',
        modulated_waveforms=36,packages_validated=12,guard_unmodified=True)
    write(out/'report.json',report);print(out);print(report['status'])


if __name__=='__main__':main()
