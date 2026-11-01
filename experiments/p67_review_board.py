"""Verify archived board bytes against NumPy and the actual host C renderer."""
import argparse,json,subprocess
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
from PIL import Image
from p45_checkpoint import ROOT,read,write,sha,rel
from p36_build_rx_full import posix

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--trial',required=True,type=Path)
    ap.add_argument('--harness',required=True,type=Path);a=ap.parse_args()
    trial=read(a.trial)
    if trial['status']!='passed_P67_RAM_RX_dashboard_120s_byte_archived_pending_review':raise ValueError('archived stopped trial required')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p67-board-review-%Y%m%dT%H%M%SZ');out.mkdir()
    r=dict(status='reviewing',trial=rel(a.trial),trial_sha256=sha(a.trial),board_operations=False,
        physical_visibility='pending_user_confirmation',RF_transmissions=0,
        scope='real RX snapshots with unknown input; not known-source RF, target OBW, or new AI accuracy')
    try:
        files=a.trial.parent/'files'
        for name,h in trial['files_sha256'].items():
            if sha(files/name)!=h:raise ValueError('archive member changed '+name)
        dashboard=read(files/'dashboard.json');summary=read(files/'summary.json');ai=read(files/'ai.json')
        rows=[json.loads(line) for line in (files/'ai-history.jsonl').read_text().splitlines()]
        if (summary['display_revision']!='p67' or summary['status']!='pass'
            or summary['reason']!='duration_complete' or summary['elapsed_software_s']<120
            or summary['display_updates']<100 or not summary['RF_after_matches']
            or not summary['worker_joined'] or not summary['buffer_released']
            or not summary['context_released'] or summary['cleanup_unconfirmed']):raise ValueError('lifecycle differs')
        sequence=summary['last_display_sequence']
        if dashboard['source_block_sequence']!=sequence or ai['source_block_sequence']!=sequence or ai['state']!='STOPPED' or dashboard['AI_state']!='STOPPED':raise ValueError('different source blocks/final state')
        if len(rows)!=summary['display_updates']+1 or any(row['accepted_class']!=-1 for row in rows) or {row['state'] for row in rows}!={'CALIBRATION_REQUIRED','STOPPED'}:raise ValueError('unexpected uncalibrated AI result')
        if any(b['elapsed_s']<=a['elapsed_s'] for a,b in zip(rows,rows[1:])):raise ValueError('nonmonotonic software clock')
        packed=np.fromfile(files/'last-display-packed.bin',dtype='<u2')
        if packed.size!=65536*2:raise ValueError('whole source block required')
        pair=(((packed&4095).astype(np.int32)^2048)-2048).astype('<i2').reshape(65536,2)
        x=pair[:8192,0].astype(float)+1j*pair[:8192,1]
        power=float(np.mean(abs(x)**2));error=abs(power-dashboard['mean_i2_q2_counts_squared'])
        if error>1e-6:raise ValueError('mean digital power differs')
        expected_relative=10*np.log10(power/dashboard['reference_first_nonzero_counts_squared'])
        if abs(expected_relative-dashboard['relative_power_db'])>1e-8:raise ValueError('relative power differs')
        w=(.5-.5*np.cos(2*np.pi*np.arange(1024)/1024)).astype(np.float32).astype(float)
        bins=np.mean(abs(np.fft.fft(x.reshape(8,1024)*w,axis=1))**2,axis=0)/(1024*np.sum(w*w))
        shifted=np.fft.fftshift(bins);cumulative=np.r_[0,np.cumsum(shifted)]
        edges=(np.arange(1025)-512-.5)*30000
        low,high=np.interp(np.array([.005,.995])*cumulative[-1],cumulative,edges)
        width_error=abs((high-low)-dashboard['record_99_percent_width_hz'])
        midpoint_error=abs((high+low)/2-dashboard['record_interval_midpoint_hz'])
        if width_error>5 or midpoint_error>5:raise ValueError('record spectral interval differs')
        source=out/'decoded-iq.bin';source.write_bytes(pair.tobytes())
        rendered=out/'host-replay';rendered.mkdir()
        q=subprocess.run(['wsl.exe','--exec',posix(a.harness),posix(source),posix(rendered),'96'],capture_output=True,timeout=30)
        (out/'replay.stdout').write_bytes(q.stdout);(out/'replay.stderr').write_bytes(q.stderr)
        if q.returncode:raise ValueError('C replay failed')
        board=np.fromfile(files/'fb.raw',dtype='<u4').reshape(480,800)
        host=np.fromfile(rendered/'render.raw',dtype='<u4').reshape(480,800)
        iq_diff=int(np.count_nonzero(board[78:209,48:369]!=host[78:209,48:369]))
        spectrum_diff=int(np.count_nonzero(board[78:209,448:781]!=host[78:209,448:781]))
        # Fixed before reading replay results: exact I/Q raster, <=1% differing
        # spectrum pixels permits host/ARM rounding at pixel boundaries.
        if iq_diff!=0 or spectrum_diff>int(131*333*.01):raise ValueError('plot source/raster differs')
        for name,pixels in [('board-final.png',board),('host-replay.png',host)]:
            rgb=np.stack(((pixels>>16)&255,(pixels>>8)&255,pixels&255),axis=-1).astype('uint8')
            Image.fromarray(rgb).save(out/name)
        r.update(status='passed_P67_board_snapshot_numerics_and_plot_parity_physical_pending',
            display_updates=summary['display_updates'],elapsed_software_s=summary['elapsed_software_s'],
            maxrss_kib=summary['maxrss_kib'],source_block_sequence=sequence,
            digital_power_absolute_error=error,record_width_error_hz=width_error,
            record_midpoint_error_hz=midpoint_error,IQ_raster_different_pixels=iq_diff,
            spectrum_raster_different_pixels=spectrum_diff,AI_rows=len(rows),
            model_SHA_unchanged=ai['model_sha256']==trial['initial_RX']['AI']['model_sha256'],
            frozen_startup_unchanged=trial['after_RX']['profile_hashes']==trial['initial_RX']['profile_hashes'],
            hardware_gaps='unknown',target_bandwidth_validated=False)
    except Exception as e:r.update(status='failed_board_review',error=repr(e))
    r['files_sha256']={rel(p):sha(p) for p in out.rglob('*') if p.is_file() and p.name!='report.json'}
    write(out/'report.json',r);print(out);print(r['status']);return int(not r['status'].startswith('passed'))
if __name__=='__main__':raise SystemExit(main())
