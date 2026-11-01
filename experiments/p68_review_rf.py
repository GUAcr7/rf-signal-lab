"""Full-history RF regression, independent Python AI and same-source LCD check."""
import argparse,collections,json,subprocess
from dataclasses import asdict
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
from PIL import Image
from p45_checkpoint import ROOT,read,write,sha,rel
from p36_build_rx_full import posix
from p37_review_archives import decode_rx12
from p48_verify_units import glyph_mask
from rfsig.rf_ai_calibration import adapt_calibrated,measure_calibration_tone
from rfsig.trainable_cnn import preprocess,patches
from rfsig.cnn_quantization import quantized_forward
from rfsig.spectrum import welch_power_spectrum
from rfsig.bandwidth import occupied_bandwidth,rrc_occupied_bandwidth_hz

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--trial',required=True,type=Path);a=ap.parse_args()
    t=read(a.trial)
    if t['status']!='passed_P68_RF_dashboard_300s_archived_pending_independent_review':raise ValueError('complete stopped archive required')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p68-review-%Y%m%dT%H%M%SZ');out.mkdir()
    r=dict(status='reviewing',trial=rel(a.trial),trial_sha256=sha(a.trial),gates=[],segments=[],shots=[],
        board_operations=False,independent_AI_accuracy=False,scope=t['scope'],
        measurement_protocol=dict(display_FFT_spacing_hz=30000,regional_band_halfwidth_hz=600000,
            center_tolerance_hz=30000,modulated_width_tolerance_hz=60000,
            noise_subtraction=False,scope='controlled known isolated source ROI only; not general target detection'))
    def check(name,ok):
        r['gates'].append(dict(name=name,passed=bool(ok)))
        if not ok:raise ValueError(name)
    try:
        files=a.trial.parent/'files'
        for name,h in t['files_sha256'].items():check('member SHA '+name,sha(files/name)==h)
        summary=read(files/'summary.json');ai=read(files/'ai.json')
        rows=[json.loads(s) for s in (files/'ai-history.jsonl').read_text().splitlines()];active=rows[:-1]
        check('build provenance',sha(ROOT/t['build'])==t['build_sha256'])
        check('source upload provenance',sha(ROOT/t['source_upload'])==t['source_upload_sha256'])
        build=read(ROOT/t['build']);frozen=read(ROOT/build['frozen'])
        for item in frozen['frozen_inputs'].values():
            check('frozen input SHA '+item['path'],sha(ROOT/item['path'])==item['sha256'])
        check('requested duration and clean stop',summary['status']=='pass' and summary['reason']=='duration_complete'
            and summary['display_revision']=='p67' and summary['elapsed_software_s']>=300
            and summary['worker_joined'] and summary['buffer_released'] and summary['context_released']
            and summary['RF_after_matches'] and not summary['cleanup_unconfirmed'])
        check('whole history and stop',len(active)==summary['display_updates'] and ai==rows[-1] and ai['state']=='STOPPED' and ai['accepted_class']==-1)
        check('boot/model/token binding',all(v['boot_id']==t['initial_RX']['boot_id'] and v['model_sha256']==frozen['frozen_inputs']['model']['sha256'] and v['calibration_token'] in ('',t['calibration_token']) for v in rows))
        times=np.array([v['elapsed_s'] for v in active]);sequences=np.array([v['source_block_sequence'] for v in active])
        check('monotonic block/time',np.all(np.diff(times)>0) and np.all(np.diff(sequences)>0))
        check('no unexplained multi-second update stall',np.max(np.diff(times))<2)
        check('no stale accepted classes',all(v['accepted_class'] in (0,1,2) if v['state']=='CLASSIFIED' else v['accepted_class']==-1 for v in rows))
        check('all native TX cleanup proofs',len(t['segments'])==4 and all(v['cleanup_verified'] for v in t['segments']) and t['RX_stopped'] and t['TX_stopped'])
        for case in t['segments']:
            selected=[v for v in active if case['score_start_s']<=v['elapsed_s']<=case['score_end_s']]
            check('stable window '+case['name'],len(selected)>=5)
            accepted=[v for v in selected if v['state']=='CLASSIFIED' and v['accepted_class']>=0]
            correct=sum(v['accepted_class']==case['expected_class'] for v in accepted)
            coverage=len(accepted)/len(selected);accuracy=correct/len(accepted) if accepted else 0
            result=dict(name=case['name'],updates=len(selected),classified=len(accepted),correct=correct,
                coverage=coverage,conditional_accuracy=accuracy,states=dict(collections.Counter(v['state'] for v in selected)))
            r['segments'].append(result)
            if case['name']=='tone':check('tone abstains',all(v['state']=='UNSUPPORTED_TONE' and v['accepted_class']==-1 for v in selected))
            else:check('controlled regression '+case['name'],coverage>=.70 and accuracy>=.90)
        end=max(v['score_end_s']+8 for v in t['segments'])
        background=[v for v in active if v['elapsed_s']>=end]
        check('post-source background abstention',len(background)>=5 and all(v['state']=='NO_USABLE_SIGNAL' and v['accepted_class']==-1 for v in background))
        with np.load(ROOT/frozen['frozen_inputs']['quantized']['path'],allow_pickle=False) as z:quant=dict(z)
        harness=ROOT/'results/p67-final-20261026T021904Z/tested-replay-harness'
        metric_gates=[]
        for shot in t['shots']:
            base='shot-'+format(shot['id'],'02d');decision=read(files/(base+'.json'))
            matches=[v for v in active if v['source_block_sequence']==decision['source_block_sequence']]
            check('same-update history '+base,len(matches)==1 and matches[0]==decision and decision==shot['AI'])
            pair=decode_rx12((files/(base+'.bin')).read_bytes())
            x=pair[:,0].astype(float)+1j*pair[:,1]
            result=dict(label=shot['label'],name=base,state=decision['state'],accepted_class=decision['accepted_class'],source_block_sequence=decision['source_block_sequence'])
            if decision['ready']:
                cal=dict(status='known_tone_common_IF_calibrated',frequency_hz=decision['common_IF_hz'],shared_across_modulation_classes=True,modulation_labels_used=False)
                frames,_=adapt_calibrated(x,sample_rate_hz=30720000,calibration=cal);frames=np.asarray(frames,dtype=np.complex64)
                dc=frames.astype(np.complex128)-frames.astype(np.complex128).mean(axis=1,keepdims=True)
                powers=(abs(dc)**2).mean(axis=1);np.testing.assert_allclose(powers,decision['frame_powers'],rtol=1e-6,atol=1e-7)
                logits=quantized_forward(patches(preprocess(frames)),quant);pred=np.argmax(logits,axis=1).tolist()
                check('independent frozen Python prediction '+base,pred==decision['raw_predictions'])
                ratio=float(min(powers)/decision['background_power_reference'])
                check('independent power ratio '+base,abs(ratio-decision['minimum_power_ratio'])<1e-6*max(1,ratio))
                try:measure_calibration_tone(x);tone=True
                except ValueError:tone=False
                clipped=np.any((pair==2047)|(pair==-2048))
                expected='CLIPPED' if clipped else 'UNSUPPORTED_TONE' if tone else 'NO_USABLE_SIGNAL' if ratio<10 else 'CLASSIFIED' if len(set(pred))==1 else 'UNCERTAIN'
                check('independent policy '+base,expected==decision['state'])
            frame=np.fromfile(files/(base+'.raw'),dtype='<u4').reshape(480,800)
            label='AI: '+((['BPSK','QPSK','16QAM'][decision['accepted_class']]+' | '+format(decision['full_policy_frontend_CNN_ms'],'.1f')+' ms') if decision['accepted_class']>=0 else decision['state'])+' | controlled 3 classes'
            mask=glyph_mask(label,ROOT/'embedded/arm_panel/font8x12.h');pixels=np.where(mask,0xff96a5b6,0xff0c0e12).astype('<u4')
            check('actual AI footer pixels '+base,np.array_equal(frame[456:468,16:16+mask.shape[1]],pixels))
            replay=out/base;replay.mkdir();decoded=replay/'decoded.bin';decoded.write_bytes(pair.astype('<i2').tobytes())
            q=subprocess.run(['wsl.exe','--exec',posix(harness),posix(decoded),posix(replay),'1'],capture_output=True,timeout=25)
            check('C same-block replay '+base,q.returncode==0)
            host=np.fromfile(replay/'render.raw',dtype='<u4').reshape(480,800)
            iq_diff=int(np.count_nonzero(frame[78:209,48:369]!=host[78:209,48:369]))
            spec_diff=int(np.count_nonzero(frame[78:209,448:781]!=host[78:209,448:781]))
            check('same-source IQ/spectrum pixels '+base,iq_diff==0 and spec_diff<131*333*.01)
            Image.frombytes('RGB',(800,480),(files/(base+'.raw')).read_bytes(),'raw','BGRX').save(out/(base+'-'+shot['label']+'.png'))
            result.update(IQ_different_pixels=iq_diff,spectrum_different_pixels=spec_diff)
            # This is an offline controlled ROI measurement. Nothing here is
            # added to the LCD or used by the classifier or signal detector.
            if shot['label'] in ('tone','bpsk','qpsk','qam16'):
                spec=welch_power_spectrum(x[:8192],30720000,1024,overlap=0)
                region=(decision['common_IF_hz']-600000,decision['common_IF_hz']+600000)
                measure=occupied_bandwidth(spec.frequency_hz,spec.psd,region,rf_lo_hz=2450000000)
                result['controlled_ROI_measurement']=asdict(measure)
                center_error=abs(measure.center_baseband_hz-decision['common_IF_hz'])
                result['center_error_vs_tone_IF_hz']=center_error
                if shot['label']!='tone':
                    expected_bw=rrc_occupied_bandwidth_hz(.99,240000,.35)
                    result['ideal_RRC_99_width_hz']=expected_bw
                    result['width_error_vs_ideal_hz']=abs(measure.bandwidth_hz-expected_bw)
                    metric_gates.append(center_error<=30000 and abs(measure.bandwidth_hz-expected_bw)<=60000)
            r['shots'].append(result)
        r.update(status='passed_P68_controlled_RF_AI_dashboard_history_pixels_Python',
            display_updates=len(active),duration_software_s=summary['elapsed_software_s'],
            maximum_update_interval_s=float(np.max(np.diff(times))),
            states=dict(collections.Counter(v['state'] for v in rows)),
            controlled_ROI_measurement_diagnostic_passed=bool(metric_gates) and all(metric_gates),
            target_measurement_on_LCD=False,known_RF_source_count=4,ADC_gaps='unknown',
            ten_minute_session=False,persistent_profile_changed=False)
    except Exception as e:r.update(status='failed_or_unconfirmed_P68_review',error=repr(e))
    r['files_sha256']={rel(p):sha(p) for p in out.rglob('*') if p.is_file() and p.name!='report.json'}
    write(out/'report.json',r);print(out);print(r['status']);return int(not r['status'].startswith('passed'))
if __name__=='__main__':raise SystemExit(main())
