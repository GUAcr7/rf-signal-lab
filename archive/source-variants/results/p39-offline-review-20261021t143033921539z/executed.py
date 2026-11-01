"""Verify archived last displayed RX prefix against independent NumPy FFT."""
import argparse
from datetime import datetime,timezone
import hashlib,json
from pathlib import Path
import numpy as np
from PIL import Image
from p32_session import ROOT
from p37_review_archives import archive_bytes,decode_rx12
from p39_run_latest_panel import validate_summary


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--board-report',type=Path,required=True)
    p.add_argument('--iq-archive',type=Path,required=True)
    p.add_argument('--fb-snapshot',type=Path)
    p.add_argument('--fb-archive',type=Path)
    args=p.parse_args()
    if bool(args.fb_snapshot)!=bool(args.fb_archive):p.error('both framebuffer reports required together')
    trial=json.loads(args.board_report.read_text('utf-8'))
    if (trial['status']!='passed_latest_buffer_RX_LCD_and_independent_idle_readback'
        or not trial['independent_final_idle_verified'] or trial['native_completion_unconfirmed']):raise ValueError('accepted completed trial required')
    summary=validate_summary(trial['native_summary'],trial['duration_ms'],trial['interval_ms'],trial['cancel_signal_sent'])
    archive,raw=archive_bytes(args.iq_archive)
    if archive['expected_boot']!=trial['expected_boot'] or len(raw)!=32768 or hashlib.sha256(raw).hexdigest()!=trial['raw_sha256']:
        raise ValueError('saved displayed prefix differs')
    iq=decode_rx12(raw)
    x=iq[:,0].astype(float)+1j*iq[:,1].astype(float)
    w=(.5-.5*np.cos(2*np.pi*np.arange(1024)/1024)).astype(np.float32)
    power=np.mean(abs(np.fft.fft(x.reshape(8,1024)*w,axis=1))**2,axis=0)/(1024*np.sum(w.astype(float)**2))
    valid=bool(np.sum(power)>0);k=int(np.argmax(power))
    ref=dict(peak_db=float(10*np.log10(max(power))) if valid else -300.,
        peak_offset_bins=(k if k<512 else k-1024) if valid else None,
        rms_per_component_counts=float(np.sqrt(np.mean(abs(x)**2)/2)),
        spectrum_power_sum_counts_squared=float(np.sum(power)))
    actual=trial['frame_metrics'][-1]
    checks=dict(peak_valid=actual['peak_valid']==valid,
        peak_db=abs(actual['peak_db']-ref['peak_db'])<.002,
        peak_bin=actual['peak_offset_bins']==ref['peak_offset_bins'],
        RMS=abs(actual['rms_per_component_counts']-ref['rms_per_component_counts'])<1e-6,
        summed_bin_power=abs(actual['spectrum_power_sum_counts_squared']-ref['spectrum_power_sum_counts_squared'])<=max(1e-8,ref['spectrum_power_sum_counts_squared']*1e-5))
    if not all(checks.values()):raise ValueError('independent numerical comparison failed')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p39-offline-review-%Y%m%dT%H%M%S%fZ');out.mkdir(exist_ok=False)
    r=dict(status='passed_archived_displayed_prefix_NumPy_review',board_operations=False,
        boot_id=trial['expected_boot'],evidence={key:dict(path=str(path.resolve()),sha256=hashlib.sha256(path.read_bytes()).hexdigest()) for key,path in vars(args).items() if path},
        native_summary=summary,actual=actual,NumPy_reference=ref,checks=checks,
        saved_prefix_frames=8192,saved_original_packed_bytes=32768,
        last_display_sequence=summary['last_display_sequence'],
        software_UI_overwrites_are_not_ADC_loss_count=True,lossless_proven=False,
        physical_LCD_animation_verified_by_this_script=False,known_target_proven=False,AI_verified=False)
    if args.fb_snapshot:
        snapshot=json.loads(args.fb_snapshot.read_text('utf-8'));fb_archive,pixels=archive_bytes(args.fb_archive)
        geometry=snapshot['native_snapshot']
        if (snapshot['expected_boot']!=trial['expected_boot'] or fb_archive['expected_boot']!=trial['expected_boot']
            or Path(snapshot['panel_report']).resolve()!=args.board_report.resolve()
            or geometry['visible']!=[800,480] or geometry['bpp']!=32 or not geometry['geometry_unchanged']
            or geometry['output_stride_bytes']!=3200 or geometry['storage']!='little_endian_BGRA_or_BGRX'
            or geometry['red']!=dict(offset=16,length=8,msb_right=0)
            or geometry['green']!=dict(offset=8,length=8,msb_right=0)
            or geometry['blue']!=dict(offset=0,length=8,msb_right=0)
            or len(pixels)!=1536000 or hashlib.sha256(pixels).hexdigest()!=snapshot['raw_sha256']):raise ValueError('framebuffer provenance/layout failed')
        Image.frombytes('RGB',(800,480),pixels,'raw','BGRX').save(out/'screen.png')
        r['screen_png']=str(out/'screen.png');r['framebuffer_is_not_physical_photo']=True
    (out/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    (out/'executed.py').write_bytes(Path(__file__).read_bytes())
    print(out);print(r['status']);print(json.dumps(checks))


if __name__=='__main__':main()
