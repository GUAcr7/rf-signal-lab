"""Independent prospective RF scoring and same-IQ Python/candidate-C replay."""
from datetime import datetime,timezone
from pathlib import Path
from p45_checkpoint import ROOT,read,write,sha,rel
from p53_build_live_ai import replace_once as sub
from p73_review_events import generate as parent_generate


def generate():
    text,parent=parent_generate()
    text=sub(text,'from rfsig.cnn_quantization import quantized_forward',
        'from rfsig.cnn_quantization import quantized_forward\nfrom p74_phase_pool import phase_pool_logits\nfrom p36_build_rx_full import posix\nfrom p68_review_rf import occupied_bandwidth,welch_power_spectrum')
    text=text.replace('passed_P73_native_events_archived_pending_independent_review','passed_P75_fresh_RF_candidate_archived_pending_independent_review')
    text=text.replace("strftime('p73-review-","strftime('p75-review-")
    text=text.replace("summary['elapsed_software_s']>=300","summary['elapsed_software_s']>=360")
    text=text.replace("len(t['segments'])==3","len(t['segments'])==5")
    text=text.replace("t['segments'][2]['score_start_s']-2 >=t['calibration_ready_elapsed']+160",
                      "t['segments'][4]['score_start_s']-2 >=t['calibration_ready_elapsed']+180")
    text=sub(text,"        host=ROOT/frozen['frozen_inputs']['host']['path']", '''        host=ROOT/build['raw_host']
        check('candidate raw C SHA',sha(host)==build['raw_host_sha256'])
        for path,digest in build['inputs_sha256'].items():check('candidate input '+path,sha(ROOT/path)==digest)
        candidate_manifest=read(ROOT/'results/p74-final-20261026T095803Z/manifest.json')['files']
        check('selected Python candidate SHA',sha(ROOT/'experiments/p74_phase_pool.py')==candidate_manifest['experiments/p74_phase_pool.py']['sha256'])
        plan=read(ROOT/t['plan'])
        check('pre-acquisition plan SHA and new seed',sha(ROOT/t['plan'])==t['plan_sha256'] and plan==t['frozen_protocol'] and plan['seed']==2026102601)
        source_report=read(ROOT/plan['source'])
        check('source package bound to plan',sha(ROOT/plan['source'])==plan['source_sha256'] and source_report['seed']==plan['seed'])
''')
    text=sub(text,'logits=quantized_forward(patches(preprocess(frames)),quant);pred=np.argmax(logits,axis=1).tolist()',
        'logits=phase_pool_logits(frames,quant);pred=np.argmax(logits,axis=1).tolist()')
    text=sub(text,"[str(host),str(files/(base+'.bin')),str(ai['common_IF_hz']),'int8']",
        "['wsl.exe','--exec',posix(host),posix(files/(base+'.bin')),str(ai['common_IF_hz']),'int8']")
    text=sub(text,"            pairs=decode_rx12((files/(base+'.bin')).read_bytes());x=pairs[:,0].astype(float)+1j*pairs[:,1]",'''            pairs=decode_rx12((files/(base+'.bin')).read_bytes());x=pairs[:,0].astype(float)+1j*pairs[:,1]
            if m['valid']:
                spec=welch_power_spectrum(x[:8192],30720000,1024,overlap=0)
                center=ai['common_IF_hz'];gold=occupied_bandwidth(spec.frequency_hz,spec.psd,(center-600000,center+600000),rf_lo_hz=2450000000)
                check('fresh ROI numerics '+base,abs(gold.bandwidth_hz-m['ROI_99_width_hz'])<=5 and abs(gold.center_baseband_hz-m['center_offset_hz'])<=5)
            else:check('invalid ROI numbers cleared '+base,all(m[k] is None for k in ('ROI_99_width_hz','center_offset_hz','LO_plus_center_hz','ROI_power_counts_squared')))
''')
    text=sub(text,"        bad=[s for s in r['shots'] if s['state']=='UNCERTAIN']",'''        # Stable background after the final TX, beyond transition margins.
        background=[x for x in active if x['elapsed_s']>=t['segments'][-1]['score_end_s']+8]
        check('final stable background abstention',len(background)>=5 and all(x['state']=='NO_USABLE_SIGNAL' and x['accepted_class']==-1 for x in background))
        initial=[x for x in active if x['elapsed_s']<t['segments'][0]['score_start_s']-3]
        check('uncalibrated initial input abstains',all(x['accepted_class']==-1 for x in initial))
        check('per-condition prospective accuracy and coverage',all(s['original_coverage_accuracy_gate_passed'] for s in r['segments'] if s['source']!='tone'))
        check('final ROI invalidated',not metrics[-1]['valid'] and metrics[-1]['LO_plus_center_hz'] is None)
        latencies=np.array([x['full_policy_frontend_CNN_ms'] for x in active if x['ready']])
        r.update(prospective_seed=plan['seed'],background_stable_observations=len(background),
                 candidate_live_RAM_verified=True,candidate_persistent_installed=False,
                 end_to_end_AI_compute_ms=dict(median=float(np.median(latencies)),p95=float(np.quantile(latencies,.95)),maximum=float(latencies.max())),
                 observed_update_interval_s=dict(median=float(np.median(np.diff(times))),p95=float(np.quantile(np.diff(times),.95)),maximum=float(np.max(np.diff(times)))))
        bad=[s for s in r['shots'] if s['state']=='UNCERTAIN']
''')
    text=text.replace('completed_P73_same_update_events_full_history_and_frozen_replay','passed_P75_prospective_RF_history_phase_replay_metrics_and_cleanup')
    text=text.replace('failed_or_unconfirmed_P73_review','failed_or_unconfirmed_P75_RF_review')
    text=text.replace("next_step='compare actual native uncertain and classified IQ; keep the model and consensus frozen'",
        "next_step='separate candidate independent heldout validation and persistent startup decision; keep P70 fallback'")
    return text,parent


if __name__=='__main__':
    text,parent=generate()
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p75-review-code-%Y%m%dT%H%M%SZ');out.mkdir()
    path=out/'executed-review.py';path.write_text(text,encoding='utf-8')
    write(out/'report.json',dict(parent=rel(parent),parent_sha256=sha(parent),code=rel(path),code_sha256=sha(path),entry_sha256=sha(Path(__file__))))
    exec(compile(text,str(path),'exec'),dict(__name__='__main__',__file__=str(path)))
