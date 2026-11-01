"""Build a portable learning-only RF kit from verified P46 raw evidence.

No hardware is contacted. Original archives stay untouched. All four complete
DMA buffers per case are exported with their boundaries and provenance intact.
"""
import argparse
import csv
from datetime import datetime,timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
import numpy as np
from p32_session import ROOT
from p37_review_archives import archive_bytes,decode_rx12


def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def read(path):return json.loads(path.read_text('utf-8'))
def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--p46-state',type=Path,default=ROOT/'results/p46-active.json')
    parser.add_argument('--control-tests',type=Path)
    args=parser.parse_args();state=read(args.p46_state)
    if state['status']!='known_RF_quality_and_tone_LCD_numerically_verified':raise ValueError('verified P46 parent required')
    inputs={}
    for name in ('trial','archives','analysis'):
        item=state['reports'][name];path=ROOT/item['path']
        if sha(path)!=item['sha256']:raise ValueError('parent evidence changed')
        inputs[name]=(path,read(path))
    trial_path,trial=inputs['trial'];archives_path,archives=inputs['archives'];analysis_path,analysis=inputs['analysis']
    if (analysis['status']!='passed_all_known_source_snapshot_quality' or analysis['trial_sha256']!=sha(trial_path)
        or analysis['archives_sha256']!=sha(archives_path) or archives['trial_sha256']!=sha(trial_path)
        or not trial['all_TX_cleanup_verified']):raise ValueError('acquisition/archive/quality chain differs')
    source_path=Path(trial['source_report']);sources=read(source_path)
    if sha(source_path)!=trial['source_report_sha256']:raise ValueError('source configuration changed')
    now=datetime.now(timezone.utc);stamp=now.strftime('%Y%m%dT%H%M%SZ')
    out=ROOT/'results'/('p47-kit-'+stamp);out.mkdir(exist_ok=False)
    kit=ROOT/'deliverables'/('rf-learning-kit-'+stamp);kit.mkdir(parents=True,exist_ok=False)
    report=dict(status='building',created_utc=now.isoformat(),directory=str(kit),inputs={k:dict(path=str(p),sha256=sha(p)) for k,(p,_) in inputs.items()},
        p46_state=dict(path=str(args.p46_state.resolve()),sha256=sha(args.p46_state)),board_operations=False,
        source_archives_modified=False,AI_inference=False,independent_ML_benchmark_eligible=False)
    (out/'executed.py').write_bytes(Path(__file__).read_bytes())
    def save():write(out/'report.json',report)
    write(ROOT/'results/p47-active.json',dict(status='building_host_only',report=str(out/'report.json'),directory=str(kit),board_operations=False));save()
    try:
        for name in ('cases','originals','evidence','previews','rfsig'):(kit/name).mkdir()
        for path in (ROOT/'host/rf_learning_kit').iterdir():
            if path.suffix in ('.py','.cmd','.md'):
                data=path.read_bytes()
                if path.suffix=='.cmd':data=data.replace(b'\r\n',b'\n').replace(b'\n',b'\r\n')
                (kit/path.name).write_bytes(data)
        # These are the existing golden references, copied byte-for-byte.
        modules=('__init__.py','bpsk.py','replay_analysis.py','bandwidth.py','power.py','spectrum.py','waterfall.py')
        for name in modules:shutil.copyfile(ROOT/'src/rfsig'/name,kit/'rfsig'/name)
        versions={name:importlib.metadata.version(name) for name in ('numpy','matplotlib')}
        (kit/'requirements.txt').write_text(''.join(f'{name}=={version}\n' for name,version in versions.items()),encoding='ascii')
        for name,(path,_) in inputs.items():shutil.copyfile(path,kit/'evidence'/(name+'-report.json'))
        shutil.copyfile(source_path,kit/'evidence/source-report.json')
        if args.control_tests:
            suites=ET.parse(args.control_tests).getroot().iter('testsuite');counts=[(int(x.get('tests','0')),int(x.get('failures','0')),int(x.get('errors','0')),int(x.get('skipped','0'))) for x in suites]
            if sum(x[0] for x in counts)<8 or any(sum(x[1:]) for x in counts):raise ValueError('all controller/integrity tests must pass without skips')
            shutil.copyfile(args.control_tests,kit/'evidence/controls-and-integrity.xml')
            report['controller_tests']=dict(path=str(args.control_tests.resolve()),sha256=sha(args.control_tests),passed=sum(x[0] for x in counts))
        (kit/'evidence/builder.py').write_bytes(Path(__file__).read_bytes())
        rows=[];records=[];labels={'tone':'TONE','bpsk':'BPSK','qpsk':'QPSK','qam16':'16QAM'}
        for key,label in labels.items():
            case=next(v for v in trial['cases'] if v['name']==key);quality=next(v for v in analysis['cases'] if v['name']==key)
            entry=next(v for v in archives['cases'] if v['name']==key);archive_path=Path(entry['report'])
            if sha(archive_path)!=entry['report_sha256']:raise ValueError('archive report changed')
            archive,raw=archive_bytes(archive_path);native=case['native_metadata']
            if (archive['expected_boot']!=trial['expected_boot'] or archive['verified_raw_sha256']!=case['raw_sha256']
                or len(raw)!=1048576 or native['sample_rate_hz']!=30720000 or native['frames_per_buffer']!=65536
                or native['completed_blocks']!=4 or not native['scan_layout_validated']
                or native['channels']!=['voltage0:I','voltage1:Q'] or native['source_format']!='le:S12/16>>0'
                or quality['status']!='passed_known_source_snapshot_quality'):
                raise ValueError('unsupported capture layout or quality')
            counts=decode_rx12(raw).astype('<i2',copy=False).reshape(4,65536,2)
            iq=(counts[:,:,0].astype(np.float32)+1j*counts[:,:,1].astype(np.float32)).astype('<c8')
            npz='cases/'+key+'.npz';meta='cases/'+key+'.json';packed='originals/'+key+'.bin'
            np.savez_compressed(kit/npz,iq_counts=counts,iq=iq,sample_rate_hz=np.array(30720000,dtype='<i8'))
            (kit/packed).write_bytes(raw);shutil.copyfile(archive_path,kit/'evidence'/('archive-'+key+'.json'))
            reference=sources['references'][key]
            metadata=dict(schema='rfsig.learning_record.v1',record_id='p46-'+stamp+'-'+key,
                source='REAL_RF_SAVED',known_label=label,label_source='known_transmitter_configuration',ai_prediction=None,
                split='unassigned_learning_only',independent_ML_benchmark_eligible=False,
                sample_rate_hz=30720000,rx_lo_hz=2450000000,rx_bandwidth_hz=18000000,rx_gain_mode='manual',rx_gain_db=0,
                tx_gain_db=-10,tx_peak_component_counts=256,tx_nominal_offset_hz=960000,
                sample_units='unscaled ADC counts; not volts or dBm',array_axes=['DMA_buffer','sample','I_then_Q'],
                shape_counts=[4,65536,2],shape_complex=[4,65536],frames_per_DMA=65536,DMA_count=4,
                nominal_DMA_duration_s=65536/30720000,ADC_gaps='unknown',lossless_proven=False,
                raw_packed_sha256=case['raw_sha256'],raw_format='le:S12/16>>0; ignore undefined high 4 bits',
                capture_session_id=trial_path.parent.name+'-'+key,source_waveform_sha256=sources['files_sha256'][key],
                source_seed=reference['seed'],source_period_samples=reference['sample_count'],source_configuration=reference,
                RX_boot=trial['expected_boot'],TX_boot=trial['TX_expected_boot'],
                software_refill_timestamps=native['timestamps'],timestamp_scope='host-software monotonic timing; not ADC timestamps',
                known_reference_quality=quality,scope='One cyclic source session per label, not an independent ML dataset')
            write(kit/meta,metadata)
            records.append(dict(key=key,label=label,npz=npz,metadata=meta,original_packed=packed))
            for b,q in enumerate(quality['buffers']):
                rows.append(dict(known_TX_label=label,ai_prediction='',split='unassigned_learning_only',DMA_block_one_based=b+1,
                    npz=npz,array_selection=f'iq[{b}]',sample_count=65536,sample_rate_hz=30720000,
                    raw_file=packed,raw_byte_offset=b*262144,raw_byte_length=262144,inter_DMA_gaps='unknown',
                    reference_evm_db=q.get('reference_evm_db',''),reference_correlation=q.get('waveform_correlation',''),
                    observed_carrier_hz=q['carrier_hz'],known_source_quality=q['status'],
                    acquisition_session=metadata['capture_session_id'],cyclic_source_SHA256=metadata['source_waveform_sha256']))
        with (kit/'index.csv').open('w',encoding='utf-8-sig',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
        manifest=dict(schema='rfsig.rf_learning_kit.v1',created_utc=now.isoformat(),source='REAL_RF_SAVED',
            hardware_required=False,AI_inference=False,independent_ML_benchmark_eligible=False,split='unassigned_learning_only',
            ADC_gaps='unknown',lossless_proven=False,records=records,verified_python=sys.version,verified_dependencies=versions,
            raw_original_bytes=4194304,decoded_complex_samples=1048576,files=[])
        def inventory():
            manifest['files']=[dict(path=p.relative_to(kit).as_posix(),bytes=p.stat().st_size,sha256=sha(p))
                for p in sorted(kit.rglob('*')) if p.is_file() and p.name!='manifest.json' and '__pycache__' not in p.parts]
            write(kit/'manifest.json',manifest)
        inventory()
        # Execute the distributed copy, not a project-only wrapper.
        preview=out/'preview-check'
        cmd=[sys.executable,str(kit/'viewer.py'),'--directory',str(kit),'--headless','--output',str(preview)]
        with (out/'preview.stdout').open('wb') as stdout,(out/'preview.stderr').open('wb') as stderr:
            child=subprocess.run(cmd,cwd=kit,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,timeout=180)
        report['preview_exit_code']=child.returncode;save()
        if child.returncode:raise ValueError('distributed viewer headless check failed')
        review=read(preview/'report.json')
        if review['status']!='passed_all_16_DMA_finite_replays_and_four_rendered_previews' or len(review['rows'])!=16:
            raise ValueError('finite replay check incomplete')
        for key in labels:shutil.copyfile(preview/(key+'.png'),kit/'previews'/(key+'.png'))
        shutil.copyfile(preview/'report.json',kit/'evidence/portable-replay-review.json');inventory()
        archive=out/'rf-learning-kit.zip'
        with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=3) as packed:
            for entry in manifest['files']:packed.write(kit/entry['path'],kit.name+'/'+entry['path'])
            packed.write(kit/'manifest.json',kit.name+'/manifest.json')
        with zipfile.ZipFile(archive) as packed:
            if packed.testzip() is not None:raise ValueError('ZIP CRC failed')
            for entry in manifest['files']:
                data=packed.read(kit.name+'/'+entry['path'])
                if len(data)!=entry['bytes'] or hashlib.sha256(data).hexdigest()!=entry['sha256']:raise ValueError('ZIP member differs')
        # Prove that extraction to a different path still runs without project files.
        with tempfile.TemporaryDirectory(prefix='p47 RF 独立 ') as temporary:
            target=Path(temporary)
            with zipfile.ZipFile(archive) as packed:
                for name in packed.namelist():
                    if not (target/name).resolve().is_relative_to(target.resolve()):raise ValueError('ZIP path outside extraction root')
                packed.extractall(target)
            extracted=target/kit.name
            for label,cmd in (
                ('standalone_example',[sys.executable,str(extracted/'example_read.py')]),
                ('standalone_replay',[sys.executable,str(extracted/'viewer.py'),'--directory',str(extracted),'--headless','--output',str(out/'standalone-preview')])):
                with (out/(label+'.stdout')).open('wb') as stdout,(out/(label+'.stderr')).open('wb') as stderr:
                    child=subprocess.run(cmd,cwd=extracted,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,timeout=180)
                if child.returncode:raise ValueError('extracted package check failed: '+label)
            standalone=read(out/'standalone-preview/report.json')
            if not Path(standalone['golden_reference_module']).is_relative_to(extracted):raise ValueError('standalone check imported project-only reference')
            report.update(extracted_to_different_Unicode_path_verified=True,standalone_example_exit_code=0,standalone_replay_exit_code=0,
                standalone_reference_came_from_extracted_kit=True,standalone_report=str(out/'standalone-preview/report.json'))
        report.update(status='passed_portable_real_RF_kit_and_all_DMA_replays',records=4,DMA_buffers=16,raw_original_bytes=4194304,
            decoded_complex_samples=1048576,manifest_sha256=sha(kit/'manifest.json'),archive=dict(path=str(archive),bytes=archive.stat().st_size,sha256=sha(archive)),
            all_ZIP_members_SHA_verified=True,ZIP_CRC_verified=True,preview_report=str(preview/'report.json'),
            interactive_GUI_clicks_verified=False,known_labels_are_AI_predictions=False)
    except Exception as error:report.update(status='failed_host_only',error=repr(error))
    save();write(ROOT/'results/p47-active.json',dict(status=report['status'],report=str(out/'report.json'),directory=str(kit),board_operations=False,
        hardware_state_last_verified_by='p46_current',hardware_state_not_rechecked_this_phase=True))
    print(out);print(report['status']);return 0 if report['status'].startswith('passed_') else 1


if __name__=='__main__':raise SystemExit(main())
