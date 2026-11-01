"""Independently replay every archived diagnostic IQ block, including failures.

Diagnostic completeness and classification coverage are separate conclusions.
No classifier thresholds, weights or board state are modified here.
"""
import argparse,collections,json,subprocess
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
    ap=argparse.ArgumentParser();ap.add_argument('--trial',required=True,type=Path);a=ap.parse_args()
    t=read(a.trial)
    if t['status']!='passed_P73_native_events_archived_pending_independent_review':
        raise ValueError('complete diagnostic archive required')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p73-review-%Y%m%dT%H%M%SZ');out.mkdir()
    r=dict(status='reviewing',trial=rel(a.trial),trial_sha256=sha(a.trial),gates=[],segments=[],shots=[],
           board_operations=False,model_modified=False,scope=t['scope'],root_cause_established=False)
    def check(name,ok):
        r['gates'].append(dict(name=name,passed=bool(ok)))
        if not ok:raise ValueError(name)
    try:
        files=a.trial.parent/'files'
        events=[json.loads(line) for line in (files/'event-history.jsonl').read_text().splitlines()]
        check('event manifest exact and bounded',events==t['events'] and 1<=len(events)<=12)
        quotas=collections.Counter((e['age_window'],e['state']) for e in events)
        check('per-state age quotas',all(n<=3 for n in quotas.values()))
        for e in events:
            base='event-'+format(e['id'],'02d');ai=read(files/(base+'.json'))
            check('event same update '+base,e['same_update_capture'] and ai['source_block_sequence']==e['source_block_sequence'] and ai['state']==e['state'])
            t['shots'].append(dict(id=e['id'],base=base,label='native-'+str(e['age_window'])+'-'+e['state'],AI=ai,trigger=None))

        for n,h in t['files_sha256'].items():check('SHA '+n,sha(files/n)==h)
        check('build report SHA',sha(ROOT/t['build'])==t['build_sha256'])
        build=read(ROOT/t['build']);frozen=read(ROOT/build['frozen'])
        for k,v in frozen['frozen_inputs'].items():check('frozen '+k,sha(ROOT/v['path'])==v['sha256'])
        previous=read(ROOT/'results/p71-final-20261026T041452Z/manifest.json')
        check('unchanged persistent selection',sha(ROOT/'configs/receiver-profile.json')==
              previous['files']['configs/receiver-profile.json']['sha256'])
        r['receiver_configuration_sha256']=sha(ROOT/'configs/receiver-profile.json')
        rows=[json.loads(l) for l in (files/'ai-history.jsonl').read_text().splitlines()]
        metrics=[json.loads(l) for l in (files/'metrics-history.jsonl').read_text().splitlines()]
        active=rows[:-1];summary=read(files/'summary.json');final=read(files/'ai.json')
        check('complete history and clean stop',len(active)==summary['display_updates'] and
              final==rows[-1] and final['state']=='STOPPED' and final['accepted_class']==-1 and
              summary['status']=='pass' and summary['reason']=='duration_complete' and
              summary['elapsed_software_s']>=300 and summary['worker_joined'] and
              summary['buffer_released'] and summary['context_released'] and summary['RF_after_matches'] and
              not summary['cleanup_unconfirmed'] and t['RX_stopped'] and t['TX_stopped'] and t['serial_closed'])
        check('same-update metrics history',len(rows)==len(metrics) and all(
            x['source_block_sequence']==m['source_block_sequence'] and x['state']==m['AI_state'] and
            x['accepted_class']==m['accepted_class'] for x,m in zip(rows,metrics)))
        check('one boot/model/token',all(x['boot_id']==t['initial_RX']['boot_id'] and
            x['model_sha256']==frozen['frozen_inputs']['model']['sha256'] and
            x['calibration_token'] in ('',t['calibration_token']) for x in rows))
        times=np.array([x['elapsed_s'] for x in active]);seq=np.array([x['source_block_sequence'] for x in active])
        check('monotonic source/time',np.all(np.diff(times)>0) and np.all(np.diff(seq)>0))
        check('three bounded TX and cleanup',len(t['segments'])==3 and all(s['cleanup_verified'] for s in t['segments']))
        check('single common IF',len({x['common_IF_hz'] for x in active if x['ready']})==1)
        check('predeclared late age',t['segments'][2]['score_start_s']-2 >=t['calibration_ready_elapsed']+160)
        for s in t['segments']:
            chosen=[x for x in active if s['score_start_s']<=x['elapsed_s']<=s['score_end_s']]
            check('stable observations '+s['phase'],len(chosen)>=5)
            accepted=[x for x in chosen if x['accepted_class']>=0]
            correct=sum(x['accepted_class']==s['expected_class'] for x in accepted)
            if s['name']=='tone':check('tone abstention',all(x['state']=='UNSUPPORTED_TONE' for x in chosen))
            item=dict(phase=s['phase'],source=s['name'],observations=len(chosen),classified=len(accepted),
                      correct=correct,coverage=len(accepted)/len(chosen),conditional_accuracy=correct/len(accepted) if accepted else None,
                      states=dict(collections.Counter(x['state'] for x in chosen)),
                      calibration_age_s=[chosen[0]['elapsed_s']-t['calibration_ready_elapsed'],chosen[-1]['elapsed_s']-t['calibration_ready_elapsed']],
                      raw_prediction_counts=dict(collections.Counter(str(x['raw_predictions']) for x in chosen)))
            item['original_coverage_accuracy_gate_passed']=None if s['name']=='tone' else item['coverage']>=.70 and item['conditional_accuracy']>=.90
            r['segments'].append(item)
        with np.load(ROOT/frozen['frozen_inputs']['quantized']['path'],allow_pickle=False) as z:quant=dict(z)
        host=ROOT/frozen['frozen_inputs']['host']['path']
        for shot in t['shots']:
            base=shot.get('base','shot-'+format(shot['id'],'02d'));ai=read(files/(base+'.json'));m=read(files/(base+'.metrics.json'))
            check('actual same history '+base,ai==shot['AI'] and sum(x==ai for x in active)==1)
            check('metric same block '+base,m['source_block_sequence']==ai['source_block_sequence'] and m['AI_state']==ai['state'])
            pairs=decode_rx12((files/(base+'.bin')).read_bytes());x=pairs[:,0].astype(float)+1j*pairs[:,1]
            result=dict(name=base,label=shot['label'],state=ai['state'],predictions=ai['raw_predictions'],
                        source_block_sequence=ai['source_block_sequence'],elapsed_s=ai['elapsed_s'],
                        trigger_state=shot.get('trigger',{}).get('state') if shot.get('trigger') else None,
                        clipping_count=int(np.count_nonzero((pairs==2047)|(pairs==-2048))),
                        raw_power_counts_squared=float(np.mean(abs(x)**2)),metrics=m)
            if ai['ready']:
                cal=dict(status='known_tone_common_IF_calibrated',frequency_hz=ai['common_IF_hz'],
                         shared_across_modulation_classes=True,modulation_labels_used=False)
                frames,_=adapt_calibrated(x,sample_rate_hz=30720000,calibration=cal);frames=np.asarray(frames,dtype=np.complex64)
                dc=frames.astype(np.complex128)-frames.astype(np.complex128).mean(axis=1,keepdims=True)
                powers=np.mean(abs(dc)**2,axis=1)
                np.testing.assert_allclose(powers,ai['frame_powers'],rtol=1e-6,atol=1e-7)
                logits=quantized_forward(patches(preprocess(frames)),quant);pred=np.argmax(logits,axis=1).tolist()
                check('Python predictions '+base,pred==ai['raw_predictions'])
                q=subprocess.run([str(host),str(files/(base+'.bin')),str(ai['common_IF_hz']),'int8'],capture_output=True,timeout=15)
                (out/(base+'-C.stdout')).write_bytes(q.stdout);(out/(base+'-C.stderr')).write_bytes(q.stderr)
                check('frozen C run '+base,q.returncode==0)
                c=np.array([np.fromstring(l,sep=',') for l in q.stdout.decode().splitlines()])
                check('frozen C prediction layout '+base,c.shape==(3,5) and c[:,4].astype(int).tolist()==pred)
                np.testing.assert_allclose(c[:,1:4],logits,rtol=1e-4,atol=5e-4)
                ratio=float(min(powers)/ai['background_power_reference'])
                check('power ratio '+base,abs(ratio-ai['minimum_power_ratio'])<=1e-6*max(1,ratio))
                try:measure_calibration_tone(x);tone=True
                except ValueError:tone=False
                expected='CLIPPED' if result['clipping_count'] else 'UNSUPPORTED_TONE' if tone else 'NO_USABLE_SIGNAL' if ratio<10 else 'CLASSIFIED' if len(set(pred))==1 else 'UNCERTAIN'
                check('independent policy '+base,expected==ai['state'])
                ordered=np.sort(logits,axis=1);norm=dc/np.sqrt(powers[:,None]);radius=abs(norm)
                result.update(Python_C_ARM_predictions_match=True,logits=logits.tolist(),
                    class_margin=(ordered[:,-1]-ordered[:,-2]).tolist(),frame_powers=powers.tolist(),minimum_power_ratio=ratio,
                    normalized_radius_CV=(radius.std(axis=1)/radius.mean(axis=1)).tolist(),
                    normalized_fourth_moment=np.mean(abs(norm)**4,axis=1).tolist())
            if (files/(base+'.raw')).exists():
                image=(files/(base+'.raw')).read_bytes();fb=np.frombuffer(image,dtype='<u4').reshape(480,800)
                label='AI: '+((['BPSK','QPSK','16QAM'][ai['accepted_class']]+' | '+format(ai['full_policy_frontend_CNN_ms'],'.1f')+' ms') if ai['accepted_class']>=0 else ai['state'])+' | controlled 3 classes'
                mask=glyph_mask(label,ROOT/'embedded/arm_panel/font8x12.h')
                check('actual footer pixels '+base,np.array_equal(fb[456:468,16:16+mask.shape[1]],np.where(mask,0xff96a5b6,0xff0c0e12).astype('<u4')))
                Image.frombytes('RGB',(800,480),image,'raw','BGRX').save(out/(base+'.png'))
            r['shots'].append(result);write(out/'report.json',r)
        bad=[s for s in r['shots'] if s['state']=='UNCERTAIN']
        r.update(status='completed_P73_same_update_events_full_history_and_frozen_replay',actual_uncertain_IQ_blocks=len(bad),
                 trigger_state_mismatch_count=sum(s['trigger_state'] is not None and s['trigger_state']!=s['state'] for s in r['shots']),
                 maximum_update_interval_s=float(np.max(np.diff(times))),display_updates=len(active),
                 common_IF_hz=next(x['common_IF_hz'] for x in active if x['ready']),
                 uncertainty_root_cause_resolved=False,classification_fix_deployed=False,
                 next_step='compare actual native uncertain and classified IQ; keep the model and consensus frozen')
    except Exception as e:r.update(status='failed_or_unconfirmed_P73_review',error=repr(e))
    r['output_sha256']={rel(p):sha(p) for p in out.iterdir() if p.name!='report.json'}
    write(out/'report.json',r);print(out);print(r['status']);return int(r['status'].startswith('failed'))


if __name__=='__main__':raise SystemExit(main())
