"""Independent NumPy review of a periodic LCD trial's archived final RX block."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image

from p32_session import ROOT
from p37_review_archives import archive_bytes, decode_rx12
from p36_full_rx_run import validate_metadata


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--board-report', type=Path, required=True)
    p.add_argument('--iq-archive', type=Path, required=True)
    p.add_argument('--fb-snapshot', type=Path, required=True)
    p.add_argument('--fb-archive', type=Path, required=True)
    args = p.parse_args()
    trial = json.loads(args.board_report.read_text('utf-8'))
    snapshot = json.loads(args.fb_snapshot.read_text('utf-8'))
    iq_archive, raw = archive_bytes(args.iq_archive)
    fb_archive, pixels = archive_bytes(args.fb_archive)
    if (trial['status'] != 'passed_periodic_RX_and_LCD_draw_with_independent_idle_readback'
            or not trial['independent_final_idle_verified'] or trial['native_completion_unconfirmed']):
        raise ValueError('accepted completed trial required')
    if any(r['expected_boot'] != trial['expected_boot'] for r in (iq_archive, snapshot, fb_archive)):
        raise ValueError('mixed boot evidence')
    if Path(snapshot['panel_report']).resolve() != args.board_report.resolve():
        raise ValueError('framebuffer parent does not describe this draw')
    final = trial['cycles'][-1]
    validate_metadata(final['native_metadata'], 1)
    if hashlib.sha256(raw).hexdigest() != final['raw_sha256'] or len(raw) != 262144:
        raise ValueError('archived IQ differs from final cycle')
    iq = decode_rx12(raw)[:8192]
    x = iq[:, 0].astype(float) + 1j*iq[:, 1].astype(float)
    window = (.5-.5*np.cos(2*np.pi*np.arange(1024)/1024)).astype(np.float32)
    power = np.mean(abs(np.fft.fft(x.reshape(8, 1024)*window, axis=1))**2, axis=0)/(1024*np.sum(window.astype(float)**2))
    k = int(np.argmax(power)); offset = k if k < 512 else k-1024
    reference = dict(peak_db=float(10*np.log10(max(power))), peak_offset_bins=offset,
                     rms_per_component_counts=float(np.sqrt(np.mean(abs(x)**2)/2)),
                     spectrum_power_sum_counts_squared=float(np.sum(power)))
    actual = trial['cycle_metrics'][-1]
    checks = dict(peak_db=abs(actual['peak_db']-reference['peak_db']) < .002,
                  peak_offset_bins=actual['peak_offset_bins']==offset,
                  rms=abs(actual['rms_per_component_counts']-reference['rms_per_component_counts']) < 1e-6,
                  summed_bin_power=abs(actual['spectrum_power_sum_counts_squared']/reference['spectrum_power_sum_counts_squared']-1) < 1e-5)
    if not all(checks.values()): raise ValueError('independent numerical comparison failed')
    geometry = snapshot['native_snapshot']
    if (snapshot['status'] != 'visible_framebuffer_bytes_saved_and_gzip_verified_board_side'
            or not geometry['geometry_unchanged'] or geometry['visible'] != [800, 480]
            or geometry['output_stride_bytes'] != 3200 or geometry['bpp'] != 32
            or geometry['storage'] != 'little_endian_BGRA_or_BGRX'
            or geometry['red'] != dict(offset=16, length=8, msb_right=0)
            or geometry['green'] != dict(offset=8, length=8, msb_right=0)
            or geometry['blue'] != dict(offset=0, length=8, msb_right=0)
            or len(pixels) != 1536000 or hashlib.sha256(pixels).hexdigest() != snapshot['raw_sha256']):
        raise ValueError('framebuffer format or bytes changed')
    out = ROOT/'results'/datetime.now(timezone.utc).strftime('p38-offline-review-%Y%m%dT%H%M%SZ')
    out.mkdir(exist_ok=False)
    Image.frombytes('RGB', (800, 480), pixels, 'raw', 'BGRX').save(out/'screen.png')
    report = dict(status='passed_final_RX_NumPy_and_framebuffer_archive_review',
                  board_operations=False, boot_id=trial['expected_boot'],
                  evidence={key: dict(path=str(path.resolve()), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
                            for key, path in vars(args).items()},
                  checks=checks, final_cycle=final['cycle'], actual=actual, NumPy_reference=reference,
                  raw_SHA256=hashlib.sha256(raw).hexdigest(), raw_bytes=len(raw),
                  retained_returned_frames=65536, analysed_prefix_frames=8192,
                  requested_cycles=trial['requested_cycles'],
                  distinct_cycle_raw_hashes=len(set(c['raw_sha256'] for c in trial['cycles'])),
                  native_elapsed_software_s=trial['native_summary']['elapsed_software_s'],
                  physical_LCD_animation_confirmed=False, continuous_RX=False,
                  lossless_proven=False, real_AI_verified=False, known_target_proven=False,
                  dBm_calibrated=False, screen_png=str((out/'screen.png').resolve()),
                  framebuffer_is_not_physical_panel_photo=True,
                  only_final_cycle_raw_archived_on_host=True)
    (out/'report.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    (out/'executed.py').write_bytes(Path(__file__).read_bytes())
    print(out); print(report['status']); print(json.dumps(checks))


if __name__ == '__main__':
    main()
