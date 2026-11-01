"""Independent full-history scoring, frozen Python replay and pixel review."""
import argparse,json,collections
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
from PIL import Image
from p45_checkpoint import ROOT,read,write,sha,rel
from p37_review_archives import decode_rx12
from p48_verify_units import glyph_mask
from rfsig.rf_ai_calibration import adapt_calibrated,measure_calibration_tone
from rfsig.trainable_cnn import preprocess,patches
from rfsig.cnn_quantization import quantized_forward

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--archive',required=True,type=Path);args=ap.parse_args()
    a=read(args.archive);t=read(ROOT/a['trial']);build=read(ROOT/t['build']);frozen=read(ROOT/build['frozen'])
    if a['status']!='passed_P56_full_history_and_IQ_pixels_byte_archived' or sha(ROOT/a['trial'])!=a['trial_sha256']:raise ValueError('complete byte archive required')
    for name,digest in a['files_sha256'].items():
        if sha(args.archive.parent/name)!=digest:raise ValueError('member changed')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p56-review-%Y%m%dT%H%M%SZ');out.mkdir()
    r=dict(status='reviewing',archive=rel(args.archive),archive_sha256=sha(args.archive),trial=a['trial'],trial_sha256=a['trial_sha256'],
        gates=[],segments=[],shots=[],board_operations=False,physical_LCD_confirmed=False,
        scope=t['scope'],not_independent_accuracy_test=True,universal_unknown_rejection=False)
    def check(label,ok):
        r['gates'].append(dict(name=label,passed=bool(ok)))
        if not ok:raise ValueError(label)
    try:
        rows=[json.loads(s) for s in (args.archive.parent/'ai-history.jsonl').read_text().splitlines()]
        active=rows[:-1];seq=np.array([v['source_block_sequence'] for v in active]);times=np.array([v['elapsed_s'] for v in active])
        check('complete update history plus explicit stop',len(active)==t['native_summary']['display_updates'] and rows[-1]['state']=='STOPPED' and rows[-1]['accepted_class']==-1)
        check('same boot model and calibration token',all(v['boot_id']==t['expected_boot'] and v['model_sha256']==frozen['frozen_inputs']['model']['sha256'] and v['calibration_token'] in ('',t['calibration_token']) for v in rows))
        check('strictly increasing consumed source blocks and elapsed time',len(rows)<4096 and np.all(np.diff(seq)>0) and np.all(np.diff(times)>0))
        check('no stale accepted class',all((v['accepted_class'] in (0,1,2) and v['raw_predictions']==[v['accepted_class']]*3) if v['state']=='CLASSIFIED' else v['accepted_class']==-1 for v in rows))
        check('each TX independently released',all(s['cleanup_verified'] for s in t['segments']) and t['TX_idle_verified'] and t['RX_idle_verified'])
        check('requested session duration reached',t['native_summary']['elapsed_software_s']>=t['duration_ms']/1000 and t['native_summary']['worker_started'] and t['native_summary']['worker_joined'])
        check('no unexplained multi-second UI stall',float(np.max(np.diff(times)))<2)
        protocol=t['acceptance_protocol'];total=classified=correct=0
        for s in t['segments']:
            selected=[v for v in active if s['score_start_s']<=v['elapsed_s']<=s['score_end_s']]
            check('steady interval has observations '+s['name'],len(selected)>=5)
            if s['expected_class']<0:
                check('pilot abstention',all(v['accepted_class']==-1 and v['state']=='UNSUPPORTED_TONE' for v in selected));continue
            known=[v for v in selected if v['accepted_class']>=0];right=sum(v['accepted_class']==s['expected_class'] for v in known)
            coverage=len(known)/len(selected);accuracy=right/len(known) if known else 0
            r['segments'].append(dict(name=s['name'],observations=len(selected),classified=len(known),correct=right,coverage=coverage,conditional_accuracy=accuracy,
                states=dict(collections.Counter(v['state'] for v in selected))))
            check('predeclared coverage '+s['name'],coverage>=protocol['known_signal_minimum_coverage'])
            check('predeclared conditional accuracy '+s['name'],accuracy>=protocol['known_signal_minimum_conditional_accuracy'])
            total+=len(selected);classified+=len(known);correct+=right
        # Conservative source-off intervals, including the final background hold.
        background=[]
        for i,s in enumerate(t['segments']):
            start=s['receiver_elapsed_anchor']+s['seconds']+2
            end=t['segments'][i+1]['receiver_elapsed_anchor']-1 if i+1<len(t['segments']) else times[-1]
            background.extend(v for v in active if start<=v['elapsed_s']<=end and v['ready'])
        check('source-off background observations retained',len(background)>=5)
        check('source-off background abstention',all(v['state']=='NO_USABLE_SIGNAL' and v['accepted_class']==-1 for v in background))
        with np.load(ROOT/frozen['frozen_inputs']['quantized']['path'],allow_pickle=False) as z:quant=dict(z)
        def pixels(rawpath,ai,label):
            raw=rawpath.read_bytes();p=np.frombuffer(raw,dtype='<u4').reshape(480,800)
            text='AI: '+(['BPSK','QPSK','16QAM'][ai['accepted_class']]+' | '+format(ai['full_policy_frontend_CNN_ms'],'.1f')+' ms' if ai['accepted_class']>=0 else ai['state'])+' | controlled 3 classes'
            mask=glyph_mask(text,ROOT/'embedded/arm_panel/font8x12.h');expected=np.where(mask,0xff96a5b6,0xff0c0e12).astype('<u4')
            check('exact footer pixels '+label,np.array_equal(p[456:468,16:16+mask.shape[1]],expected))
            path=out/(label+'.png');Image.frombytes('RGB',(800,480),raw,'raw','BGRX').save(path);return rel(path)
        for path in sorted(args.archive.parent.glob('shot-*.json')):
            ai=read(path);base=path.with_suffix('');pairs=decode_rx12(base.with_suffix('.bin').read_bytes());x=pairs[:,0].astype(float)+1j*pairs[:,1]
            item=dict(name=base.name,state=ai['state'],accepted_class=ai['accepted_class'],source_block_sequence=ai['source_block_sequence'])
            matches=[v for v in active if v['source_block_sequence']==ai['source_block_sequence']]
            check('snapshot decision in full history '+base.name,len(matches)==1 and matches[0]==ai)
            if ai['ready']:
                c=dict(status='known_tone_common_IF_calibrated',frequency_hz=ai['common_IF_hz'],shared_across_modulation_classes=True,modulation_labels_used=False)
                frames,_=adapt_calibrated(x,sample_rate_hz=30720000,calibration=c);frames=np.asarray(frames,dtype=np.complex64)
                # Match the C float stage before its double DC/power calculation.
                dc=frames.astype(np.complex128)-frames.astype(np.complex128).mean(axis=1,keepdims=True)
                powers=(abs(dc)**2).mean(axis=1)
                np.testing.assert_allclose(ai['frame_powers'],powers,rtol=1e-6,atol=1e-7)
                logits=quantized_forward(patches(preprocess(frames)),quant);pred=np.argmax(logits,axis=1).tolist()
                check('snapshot frozen Python class replay '+base.name,pred==ai['raw_predictions'])
                ratio=float(min(powers)/ai['background_power_reference']);check('snapshot power ratio '+base.name,abs(ratio-ai['minimum_power_ratio'])<=1e-6*max(1,ratio))
                try:measure_calibration_tone(x);tone=True
                except ValueError:tone=False
                clipped=np.any((pairs==2047)|(pairs==-2048))
                expected='CLIPPED' if clipped else 'UNSUPPORTED_TONE' if tone else 'NO_USABLE_SIGNAL' if ratio<10 else 'CLASSIFIED' if len(set(pred))==1 else 'UNCERTAIN'
                check('snapshot independent policy '+base.name,expected==ai['state'])
                item['Python_frontend_and_policy_checked']=True
            item['screen']=pixels(base.with_suffix('.raw'),ai,base.name);r['shots'].append(item)
        r['final_screen']=pixels(args.archive.parent/'fb.raw',t['final_AI'],'final-stopped')
        r.update(status='passed_controlled_runtime_AI_full_history_pixels_and_Python_replay',display_updates=len(active),session_seconds=t['native_summary']['elapsed_software_s'],
            maximum_update_interval_s=float(np.max(np.diff(times))),known_signal_observations=total,classified_observations=classified,correct_observations=correct,
            coverage=classified/total,conditional_accuracy=correct/classified,source_off_observations=len(background),
            states=dict(collections.Counter(v['state'] for v in rows)),policy_ms_median=float(np.median([v['full_policy_frontend_CNN_ms'] for v in active if v['ready']])),
            ten_minute_duration_verified=t['duration_ms']>=600000)
    except Exception as e:r.update(status='failed_or_unconfirmed_runtime_AI_review',error=repr(e))
    write(out/'report.json',r);print(out);print(r['status']);return int(not r['status'].startswith('passed'))
if __name__=='__main__':raise SystemExit(main())
