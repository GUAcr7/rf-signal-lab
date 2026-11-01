"""Review complete production history without weakening the failed AI gate."""
from datetime import datetime,timezone
import json
import numpy as np
from PIL import Image
from p45_checkpoint import ROOT,read,write,sha,rel
from p48_verify_units import glyph_mask

def main():
    pointer=read(ROOT/'results/p70-stopped-archive-active.json');path=ROOT/pointer['report'];a=read(path)
    if (sha(path)!=pointer['report_sha256'] or a['status']!='passed_P70_stopped_data_archived'
        or len(a.get('files_sha256',{}))!=8 or len(a.get('chunks',[]))<1):raise ValueError('real byte archive required, not a console marker')
    demo_path=ROOT/'results/p59-demo-20261026T031526886336Z/report.json';demo=read(demo_path)
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p70-review-%Y%m%dT%H%M%SZ');out.mkdir()
    r=dict(status='reviewing',archive=rel(path),archive_sha256=sha(path),demo=rel(demo_path),demo_sha256=sha(demo_path),
        board_operations=False,groups=[],cold_power_cycle_verified=False)
    try:
        files=path.parent/'files'
        for name,h in a['files_sha256'].items():
            if sha(files/name)!=h:raise ValueError('archive changed '+name)
        ai=[json.loads(s) for s in (files/'ai-history.jsonl').read_text().splitlines()]
        metrics=[json.loads(s) for s in (files/'metrics-history.jsonl').read_text().splitlines()]
        summary=read(files/'summary.json');last=read(files/'metrics.json')
        if (len(ai)!=len(metrics) or len(ai)!=summary['display_updates']+1
            or summary['status']!='stopped' or summary['reason']!='signal_requested_stop'
            or not all(summary[k] for k in ('buffer_released','context_released','worker_joined','RF_after_matches'))
            or ai[-1]['state']!='STOPPED' or last['valid'] or last['measurement_status']!='STOPPED'):raise ValueError('stop/cleanup failed')
        for m,d in zip(metrics,ai):
            if m['source_block_sequence']!=d['source_block_sequence'] or m['AI_state']!=d['state']:raise ValueError('wrong metric source')
            if not m['valid'] and any(m[k] is not None for k in ('LO_plus_center_hz','ROI_99_width_hz','ROI_power_counts_squared')):raise ValueError('stale invalid value')
        for step in demo['steps']:
            if step['action']!='send':continue
            source=ROOT/step['report'];s=read(source)
            if sha(source)!=step['report_sha256'] or not s['TX_cleanup_verified']:raise ValueError('source/cleanup evidence changed')
            anchor=s['AI_observations'][0]['elapsed_s']
            rows=[v for v in ai if anchor+2<=v['elapsed_s']<=anchor+s['TX_seconds']-3]
            accepted=[v for v in rows if v['state']=='CLASSIFIED'];expected={'bpsk':0,'qpsk':1,'qam16':2}.get(s['source_truth'],-1)
            correct=sum(v['accepted_class']==expected for v in accepted)
            coverage=len(accepted)/len(rows);accuracy=correct/len(accepted) if accepted else 0
            passed=all(v['state']=='UNSUPPORTED_TONE' for v in rows) if expected<0 else coverage>=.7 and accuracy>=.9
            r['groups'].append(dict(name=s['source_truth'],updates=len(rows),accepted=len(accepted),correct=correct,
                uncertain=sum(v['state']=='UNCERTAIN' for v in rows),coverage=coverage,conditional_accuracy=accuracy,passed=passed))
        pixels=np.fromfile(files/'fb.raw',dtype='<u4').reshape(480,800)
        for y,label in ((286,'State: STOPPED'),(308,'LO+center: unavailable'),(328,'99% ROI BW: unavailable')):
            mask=glyph_mask(label,ROOT/'embedded/arm_panel/font8x12.h');colour=0xffdee6ee if y==286 else 0xff96a5b6
            if not np.array_equal(pixels[y:y+12,456:456+mask.shape[1]],np.where(mask,colour,0xff0c0e12).astype('<u4')):raise ValueError('stop-screen metric text')
        Image.frombytes('RGB',(800,480),(files/'fb.raw').read_bytes(),'raw','BGRX').save(out/'production-stopped.png')
        r.update(status='reviewed_P70_warm_startup_metrics_with_16QAM_coverage_failure',display_updates=summary['display_updates'],
            all_RF_AI_gates_passed=all(g['passed'] for g in r['groups']),metrics_invalidation_passed=True,
            cleanup_passed=True,model_changed=False,thresholds_relaxed=False,
            known_issue='16QAM unanimity rejects disagreeing subframes; complete stable history confirms coverage failure; cause not yet established',
            rejected_prior_archive_report='results/p59-p70-halt-20261026T032359473867Z/report.json',
            rejected_prior_archive_reason='console terminator mistaken for existing archive; no files/chunks; corrected parser and real 8-file archive used')
    except Exception as e:r.update(status='failed_P70_archive_review',error=repr(e))
    write(out/'report.json',r);print(out);print(r['status']);return int(r['status'].startswith('failed'))
if __name__=='__main__':raise SystemExit(main())
