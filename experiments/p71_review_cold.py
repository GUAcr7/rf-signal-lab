"""Independent cold-session bytes, FFT, stop glyphs and startup identity review."""
from datetime import datetime,timezone
import json
import numpy as np
from PIL import Image
from p45_checkpoint import ROOT,read,write,sha,rel
from p37_review_archives import decode_rx12
from p48_verify_units import glyph_mask
from p70_cold_prepare import passive_startup_ready

def main():
    trial=ROOT/'results/p59-p71-cold-20261026T040825188668Z/report.json';t=read(trial)
    if t['status']!='passed_P71_user_cold_autonomous_ROI_10min_RX_stopped':raise ValueError('complete cold archive required')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p71-review-%Y%m%dT%H%M%SZ');out.mkdir()
    r=dict(status='reviewing',trial=rel(trial),trial_sha256=sha(trial),board_operations=False)
    try:
        passive=ROOT/t['passive'];p=read(passive)
        raw=(passive.parent/'uart.rx.bin').read_bytes();sent=(passive.parent/'uart.tx.bin').read_bytes()
        if sha(passive)!=t['passive_sha256'] or sent or not passive_startup_ready(raw.decode('ascii',errors='replace')):raise ValueError('passive proof changed')
        if not read(ROOT/t['human'])['new_board_powercycled_by_user'] or not read(ROOT/t['halt'])['halt_observed']:raise ValueError('physical action/halt proof')
        files=trial.parent/'files'
        for name,h in t['files_sha256'].items():
            if sha(files/name)!=h:raise ValueError('archive changed '+name)
        ai=[json.loads(s) for s in (files/'ai-history.jsonl').read_text().splitlines()]
        metrics=[json.loads(s) for s in (files/'metrics-history.jsonl').read_text().splitlines()]
        summary=read(files/'summary.json');progress=read(files/'progress.json')
        if len(ai)!=summary['display_updates']+1 or len(ai)!=len(metrics) or summary['elapsed_software_s']<630:raise ValueError('duration/history incomplete')
        if any(a['boot_id']!=t['expected_boot'] or a['state']!='CALIBRATION_REQUIRED' or a['ready'] or a['accepted_class']!=-1 for a in ai[:-1]):raise ValueError('stale calibration/classification')
        if ai[-1]['state']!='STOPPED' or any(m['valid'] for m in metrics):raise ValueError('stale current measurement')
        if any(a['source_block_sequence']!=m['source_block_sequence'] for a,m in zip(ai,metrics)):raise ValueError('AI/metric block mismatch')
        pair=decode_rx12((files/'last-display-packed.bin').read_bytes());x=pair[:8192,0].astype(float)+1j*pair[:8192,1]
        window=(.5-.5*np.cos(2*np.pi*np.arange(1024)/1024)).astype(np.float32).astype(float)
        bins=np.mean(abs(np.fft.fft(x.reshape(8,1024)*window,axis=1))**2,axis=0)/(1024*np.sum(window*window))
        peak_db=10*np.log10(max(bins));rms=float(np.sqrt(np.mean(abs(x)**2)/2))
        if abs(peak_db-progress['peak_db'])>.002 or abs(rms-progress['rms_per_component_counts'])>1e-6:raise ValueError('FFT/power reference mismatch')
        for key in ('worker_joined','buffer_released','context_released','RF_after_matches'):
            if not summary[key]:raise ValueError('cleanup '+key)
        image=np.fromfile(files/'fb.raw',dtype='<u4').reshape(480,800)
        for y,label,colour in ((286,'State: STOPPED',0xffdee6ee),(308,'LO+center: unavailable',0xff96a5b6),
            (328,'99% ROI BW: unavailable',0xff96a5b6),(456,'AI: STOPPED | controlled 3 classes',0xff96a5b6)):
            mask=glyph_mask(label,ROOT/'embedded/arm_panel/font8x12.h');left=16 if y==456 else 456
            if not np.array_equal(image[y:y+12,left:left+mask.shape[1]],np.where(mask,colour,0xff0c0e12).astype('<u4')):raise ValueError('final actual glyph mismatch')
        Image.frombytes('RGB',(800,480),(files/'fb.raw').read_bytes(),'raw','BGRX').save(out/'cold-final-stopped.png')
        human=read(ROOT/'results/p71-human-screen-20261026.json')
        r.update(status='passed_P71_cold_history_FFT_pixels_cleanup_review',true_power_cycle_verified=True,
            autonomous_duration_s=summary['elapsed_software_s'],display_updates=summary['display_updates'],
            peak_bin_power_error_db=abs(peak_db-progress['peak_db']),RMS_error_counts=abs(rms-progress['rms_per_component_counts']),
            screen_lit_after_session=human['screen_lit_after_session_confirmed'],human_dynamic_motion_this_cycle=False,
            passive_parser_false_negative_resolved_without_new_power_cycle=True,
            first_cached_state_failure='results/p59-p71-cold-20261026T040119819048Z/report.json',
            first_failure_reason='caller used the pre-stop boards snapshot; actual RX stopped and same unchanged 668s session was archived after refreshing state',
            AI_16QAM_acceptance_issue_still_open=True,host_RX_starts=0,RF_transmissions=0)
    except Exception as e:r.update(status='failed_P71_cold_review',error=repr(e))
    write(out/'report.json',r);print(out);print(r['status']);return int(r['status'].startswith('failed'))
if __name__=='__main__':raise SystemExit(main())
