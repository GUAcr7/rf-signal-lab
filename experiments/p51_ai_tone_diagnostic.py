"""Frozen-input diagnostic on already-seen P46 RF; never an independent benchmark."""
import argparse,json,subprocess
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
from p45_checkpoint import ROOT,read,write,sha,rel
from rfsig.rf_ai_calibration import adapt_calibrated
from p37_review_archives import archive_bytes,decode_rx12
from rfsig.rf_ai_input import adapt_dma_block,anti_alias_taps,SAMPLE_RATE_HZ,NOMINAL_IF_HZ
from rfsig.trainable_cnn import preprocess,patches,forward
from rfsig.cnn_quantization import quantized_forward

MODEL_SHA='cf24285e41c9b113fd05e56498c47292884f3b792a6b097e8fe2afb0a469869b'
CLASSES=('BPSK','QPSK','16QAM')
NAMES=('bpsk','qpsk','qam16')


def freeze(calibration_path):
    paths=dict(calibration=calibration_path,calibrated_adapter=ROOT/'src/rfsig/rf_ai_calibration.py',model=ROOT/'results/p09-trained-cnn-20261011T055334Z/cnn-model.npz',
        quantized_model=ROOT/'results/p10-trained-cnn-20261011T055826Z/quantized-model.npz',
        host_C=ROOT/'results/p10-trained-cnn-20261011T055826Z/trained-cnn-host.exe',
        state=ROOT/'results/p46-active.json',adapter=ROOT/'src/rfsig/rf_ai_input.py',
        preprocess=ROOT/'src/rfsig/trainable_cnn.py',quantization=ROOT/'src/rfsig/cnn_quantization.py',
        script=Path(__file__),adapter_tests=ROOT/'results/p51-ai-adapter-tests-20261023.xml')
    if sha(paths['model'])!=MODEL_SHA:raise ValueError('frozen accepted CNN required')
    state=read(paths['state'])
    for key in ('trial','archives'):
        paths[key]=ROOT/state['reports'][key]['path']
        if sha(paths[key])!=state['reports'][key]['sha256']:raise ValueError('P46 parent changed')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p51-ai-tone-plan-%Y%m%dT%H%M%SZ');out.mkdir()
    plan=dict(status='frozen_before_RF_diagnostic_predictions',created_utc=datetime.now(timezone.utc).isoformat(),
        inputs={k:dict(path=rel(v),sha256=sha(v)) for k,v in paths.items()},class_order=list(CLASSES),
        protocol=dict(sample_rate_hz=SAMPLE_RATE_HZ,common_nominal_IF_hz=NOMINAL_IF_HZ,
            decimation=16,output_rate_hz=1920000,controlled_symbol_rate_hz=240000,samples_per_symbol=8,
            FIR_taps=513,cutoff_hz=480000,kaiser_beta=8.6,frame_length=1024,phase_offset_selection='none',
            frequency_fitting='one tone-only common calibration; no per-class fits',normalization='frozen per-frame complex DC/RMS',
            DMA_handling='separate valid convolution per returned buffer; discard tails; no concatenation'),
        model_weights_modified=False,independent_real_RF_accuracy='not_measured',
        scope='Already-seen P46 periodic sources, one seed/session per class. Diagnostic only; no training or parameter selection.',
        excluded_tone='outside the frozen three-class vocabulary; no unknown rejection implemented',board_operations=False)
    plan['protocol']['common_calibrated_IF_hz']=read(calibration_path)['calibration']['frequency_hz']
    write(out/'report.json',plan);print(out);return out/'report.json'


def load_plan(path):
    plan=read(path)
    if plan['status']!='frozen_before_RF_diagnostic_predictions' or plan['class_order']!=list(CLASSES):raise ValueError('frozen diagnostic plan required')
    inputs={k:ROOT/v['path'] for k,v in plan['inputs'].items()}
    if any(sha(inputs[k])!=v['sha256'] for k,v in plan['inputs'].items()):raise ValueError('frozen input changed')
    return plan,inputs


def diagnose(path):
    plan,inputs=load_plan(path);trial=read(inputs['trial']);archives=read(inputs['archives'])
    if (archives['status']!='passed_all_known_source_raw_buffers_archived' or archives['trial_sha256']!=sha(inputs['trial'])
        or trial['status']!='passed_bounded_known_source_captures_pending_host_archive' or not trial['all_TX_cleanup_verified']):
        raise ValueError('complete original RF acquisition/archive chain required')
    sources_path=Path(trial['source_report']);sources=read(sources_path)
    if sha(sources_path)!=trial['source_report_sha256']:raise ValueError('source metadata changed')
    for name in NAMES:
        ref=sources['references'][name]
        if (ref['sample_rate_hz']!=SAMPLE_RATE_HZ or ref['offset_hz']!=NOMINAL_IF_HZ
            or ref['samples_per_symbol']!=128 or ref['symbol_rate_hz']!=240000):raise ValueError('fixed common RF conditions differ')
    with np.load(inputs['model'],allow_pickle=False) as z:model=dict(z)
    with np.load(inputs['quantized_model'],allow_pickle=False) as z:quantized=dict(z)
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p51-ai-tone-diagnostic-%Y%m%dT%H%M%SZ');out.mkdir();(out/'inputs').mkdir();(out/'outputs').mkdir()
    report=dict(status='running_diagnostic',plan=rel(path),plan_sha256=sha(path),cases=[],
        model_sha256=MODEL_SHA,board_operations=False,model_weights_modified=False,live_RX_connected=False,
        independent_real_RF_accuracy='not_measured',scope=plan['scope'],unknown_rejection=False)
    (out/'executed.py').write_bytes(Path(__file__).read_bytes());write(out/'report.json',report)
    calibration=read(inputs['calibration'])['calibration']
    all_frames=[];truth=[];frame_ids=[]
    for name in NAMES:
        entry=next(c for c in archives['cases'] if c['name']==name);capture=next(c for c in trial['cases'] if c['name']==name)
        archive=Path(entry['report'])
        if sha(archive)!=entry['report_sha256']:raise ValueError('archive report changed')
        meta,raw=archive_bytes(archive);native=capture['native_metadata']
        if (meta['expected_boot']!=trial['expected_boot'] or meta['verified_raw_sha256']!=capture['raw_sha256']
            or native['source_format']!='le:S12/16>>0' or not native['scan_layout_validated']
            or native['frames_per_buffer']!=65536 or native['frame_bytes']!=4
            or native['channels']!=['voltage0:I','voltage1:Q'] or not native['complete_returned_buffers_saved']
            or len(raw)!=capture['blocks']*65536*4):raise ValueError('packed RX1 block layout differs')
        iq=decode_rx12(raw);iq=iq[:,0].astype(float)+1j*iq[:,1]
        case=dict(name=name,archive=rel(archive),archive_sha256=sha(archive),blocks=[],
            source_seed=sources['references'][name]['seed'],training_test_independence=False)
        for index,x in enumerate(iq.reshape(capture['blocks'],65536)):
            timestamp=native['timestamps'][index]
            if timestamp['block_index']!=index or timestamp['file_byte_offset']!=index*65536*4 or not timestamp['copy_complete']:
                raise ValueError('DMA mapping differs')
            frames,details=adapt_calibrated(x,sample_rate_hz=SAMPLE_RATE_HZ,calibration=calibration)
            case['blocks'].append(dict(block=index,**details))
            for j,frame in enumerate(frames):
                frame_id=f'{name}-b{index:02}-f{j:02}';model_input=np.asarray(frame,dtype='<c8')
                file=out/'inputs'/(frame_id+'.iq');np.column_stack((model_input.real,model_input.imag)).astype('<f4').tofile(file)
                all_frames.append(model_input);truth.append(NAMES.index(name));frame_ids.append(frame_id)
        report['cases'].append(case)
    frames=np.asarray(all_frames);p=patches(preprocess(frames));references=dict(fp32=forward(p,model),int8=quantized_forward(p,quantized))
    report['inference']={}
    for mode,logits in references.items():
        actual=[]
        for i,frame_id in enumerate(frame_ids):
            child=subprocess.run([str(inputs['host_C']),str(out/'inputs'/(frame_id+'.iq')),mode],capture_output=True,timeout=10)
            (out/'outputs'/(frame_id+'-'+mode+'.txt')).write_bytes(child.stdout)
            if child.returncode:raise ValueError('frozen host C failed: '+child.stderr.decode(errors='replace'))
            values=np.fromstring(child.stdout.decode().strip(),sep=',')
            if values.shape!=(4,) or not np.isfinite(values).all():raise ValueError('C result shape differs')
            np.testing.assert_allclose(values[:3],logits[i],rtol=1e-4 if mode=='fp32' else 0,atol=5e-4 if mode=='fp32' else 1e-10)
            if int(values[3])!=int(np.argmax(logits[i])):raise ValueError('C and Python prediction differ')
            actual.append(int(values[3]))
        confusion=np.zeros((3,3),int)
        for a,b in zip(truth,actual):confusion[a,b]+=1
        report['inference'][mode]=dict(diagnostic_frames=len(actual),correct=int(np.trace(confusion)),
            descriptive_fraction_correct=float(np.trace(confusion)/len(actual)),confusion_rows_truth_cols_prediction=confusion.tolist(),
            host_C_Python_logits_and_predictions_match=True,calibrated_confidence=False)
    np.savez_compressed(out/'diagnostic.npz',frames=frames,truth=np.array(truth),frame_id=np.array(frame_ids),**references)
    report.update(status='passed_frozen_RF_adapter_and_C_Python_parity_diagnostic_only',frames=len(frames),
        unique_transmitted_waveforms_per_class=1,source_repeat_does_not_create_independence=True,
        independent_acquisition_sessions_per_class=1,raw_files_modified=False,
        outputs_sha256={rel(f):sha(f) for folder in ('inputs','outputs') for f in (out/folder).iterdir()},dataset_sha256=sha(out/'diagnostic.npz'))
    write(out/'report.json',report);print(out);print(report['status']);print(json.dumps(report['inference']))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--calibration',type=Path);g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--freeze-plan',action='store_true');g.add_argument('--plan',type=Path);args=p.parse_args()
    if args.freeze_plan:
        if not args.calibration:p.error('tone calibration required before freezing')
        freeze(args.calibration)
    else:diagnose(args.plan)


if __name__=='__main__':main()
