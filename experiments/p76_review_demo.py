"""Independent installed-session history, source gates, FFT and stop pixels."""
import argparse,json
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
from PIL import Image
from p45_checkpoint import ROOT,read,write,sha,rel
from p37_review_archives import decode_rx12
from p48_verify_units import glyph_mask


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--demo',required=True,type=Path);a=ap.parse_args();t=read(a.demo)
    if t['status']!='passed_P76_installed_autonomous_10min_RF_full_history_stopped':raise ValueError('complete installed session required')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p76-review-%Y%m%dT%H%M%SZ');out.mkdir()
    r=dict(status='reviewing_P76',demo=rel(a.demo),demo_sha256=sha(a.demo),board_operations=False,gates=[])
    def gate(name,ok):
        r['gates'].append(dict(name=name,passed=bool(ok)))
        if not ok:raise ValueError(name)
    try:
        boot_path=ROOT/t['boot'];boot=read(boot_path)
        gate('immutable warm proof',sha(boot_path)==t['boot_sha256'] and boot['status']=='passed_P76_warm_boot_autonomous_phase_AI_display')
        gate('board-init autonomous app',t['host_RX_starts']==0 and boot['monitor_started_by_board_init'] and boot['reboots_issued']==1 and boot['expected_boot']==t['expected_boot'])
        gate('new boot cleared calibration',boot['startup_RX']['AI']['state']=='CALIBRATION_REQUIRED' and not boot['startup_RX']['AI']['ready'] and not boot['startup_metrics']['valid'])
        selection=read(ROOT/'configs/receiver-profile.json')
        gate('computer selected exact startup certificate',selection['report']==rel(boot_path) and selection['report_sha256']==sha(boot_path))
        files=a.demo.parent/'files'
        for name,digest in t['files_sha256'].items():gate('archived SHA '+name,sha(files/name)==digest)
        ai=[json.loads(s) for s in (files/'ai-history.jsonl').read_text().splitlines()]
        metrics=[json.loads(s) for s in (files/'metrics-history.jsonl').read_text().splitlines()]
        summary=read(files/'summary.json');progress=read(files/'progress.json')
        gate('complete 630s stopped session',len(ai)==len(metrics)==summary['display_updates']+1 and summary['elapsed_software_s']>=630 and summary['display_revision']=='p75' and summary['reason']=='signal_requested_stop' and summary['status']=='stopped')
        gate('clean resource release',all(summary[k] for k in ('worker_joined','buffer_released','context_released','RF_after_matches')) and not summary['cleanup_unconfirmed'] and t['TX_stopped'] and t['RX_stopped'] and t['serial_closed'])
        gate('one live boot and original weights',all(x['boot_id']==t['expected_boot'] and x['model_sha256']=='bd571ef0d30b76cdb8138d3ebd90f55463eb5439bd4c78636555bc8800873457' for x in ai))
        gate('AI and metric source identity',all(x['source_block_sequence']==m['source_block_sequence'] and x['state']==m['AI_state'] and x['accepted_class']==m['accepted_class'] for x,m in zip(ai,metrics)))
        gate('invalid numbers always cleared',all(m['valid'] or all(m[k] is None for k in ('LO_plus_center_hz','ROI_99_width_hz','ROI_power_counts_squared','center_offset_hz')) for m in metrics))
        gate('stop cleared class and numbers',ai[-1]['state']=='STOPPED' and ai[-1]['accepted_class']==-1 and not metrics[-1]['valid'])
        groups=[]
        for step in t['steps']:
            if step['action']!='send':continue
            p=ROOT/step['report'];s=read(p)
            gate('source cleanup '+step['signal'],sha(p)==step['report_sha256'] and s['TX_cleanup_verified'])
            start=s['AI_observations'][0]['elapsed_s']
            rows=[x for x in ai[:-1] if start+2<=x['elapsed_s']<=start+step['seconds']-3]
            accepted=[x for x in rows if x['accepted_class']>=0]
            truth={'bpsk':0,'qpsk':1,'qam16':2}.get(step['signal'],-1)
            correct=sum(x['accepted_class']==truth for x in accepted)
            coverage=len(accepted)/len(rows) if rows else 0;accuracy=correct/len(accepted) if accepted else 0
            passed=len(rows)>=5 and (all(x['state']=='UNSUPPORTED_TONE' for x in rows) if truth<0 else coverage>=.7 and accuracy>=.9)
            groups.append(dict(source=step['signal'],updates=len(rows),accepted=len(accepted),correct=correct,coverage=coverage,conditional_accuracy=accuracy,passed=passed))
            gate('full-history signal gate '+step['signal'],passed)
        gate('all four source groups scored',groups==t['groups'] and len(groups)==4)
        times=np.array([x['elapsed_s'] for x in ai[:-1]]);seq=np.array([x['source_block_sequence'] for x in ai[:-1]])
        gate('fresh advancing updates',np.all(np.diff(times)>0) and np.all(np.diff(seq)>0) and np.max(np.diff(times))<2)
        pair=decode_rx12((files/'last-display-packed.bin').read_bytes());x=pair[:8192,0].astype(float)+1j*pair[:8192,1]
        window=(.5-.5*np.cos(2*np.pi*np.arange(1024)/1024)).astype(np.float32).astype(float)
        power=np.mean(abs(np.fft.fft(x.reshape(8,1024)*window,axis=1))**2,axis=0)/(1024*np.sum(window*window))
        peak_db=10*np.log10(max(power));rms=float(np.sqrt(np.mean(abs(x)**2)/2))
        gate('final FFT and RMS same source',abs(peak_db-progress['peak_db'])<.002 and abs(rms-progress['rms_per_component_counts'])<1e-6)
        pixels=np.fromfile(files/'fb.raw',dtype='<u4').reshape(480,800)
        for y,label,color,left in ((286,'State: STOPPED',0xffdee6ee,456),(308,'LO+center: unavailable',0xff96a5b6,456),
            (328,'99% ROI BW: unavailable',0xff96a5b6,456),(456,'AI: STOPPED | controlled 3 classes',0xff96a5b6,16)):
            mask=glyph_mask(label,ROOT/'embedded/arm_panel/font8x12.h')
            gate('stop framebuffer '+label,np.array_equal(pixels[y:y+12,left:left+mask.shape[1]],np.where(mask,color,0xff0c0e12).astype('<u4')))
        Image.frombytes('RGB',(800,480),(files/'fb.raw').read_bytes(),'raw','BGRX').save(out/'installed-stopped.png')
        r.update(status='passed_P76_installed_10min_RF_history_FFT_pixels_cleanup',groups=groups,
                 elapsed_software_s=summary['elapsed_software_s'],display_updates=summary['display_updates'],
                 maximum_update_interval_s=float(np.max(np.diff(times))),new_independent_accuracy_claimed=False,
                 physical_LCD_confirmed=False,true_power_cycle_verified=False,
                 receiver_selection_sha256=sha(ROOT/'configs/receiver-profile.json'),
                 release_scope='controlled_competition_demo',next_task='saved halt and one actual power cycle if final cold confirmation required')
    except Exception as exc:r.update(status='failed_or_unconfirmed_P76_review',error=repr(exc))
    write(out/'report.json',r);print(out);print(r['status'])


if __name__=='__main__':main()
