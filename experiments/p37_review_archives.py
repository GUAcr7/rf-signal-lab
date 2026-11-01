"""Verify saved P37 evidence and decode packed RX12 without touching a board."""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image

from p32_session import ROOT


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_report(path):
    return json.loads(path.read_text(encoding='utf-8'))


def archive_bytes(path):
    report = read_report(path)
    if report['status'] != 'compressed_and_raw_bytes_archived_identity_and_source_rechecked':
        raise ValueError('complete archive required')
    raw = (path.parent / report['local_raw_file']).read_bytes()
    packed = (path.parent / report['local_compressed_file']).read_bytes()
    if (len(raw) != report['verified_raw_bytes'] or sha(raw) != report['verified_raw_sha256']
            or len(packed) != report['compressed_bytes']
            or sha(packed) != report['compressed_sha256'] or gzip.decompress(packed) != raw):
        raise ValueError('archive bytes, gzip CRC or SHA changed')
    return report, raw


def decode_rx12(raw):
    # le:S12/16>>0: padding bits are undefined, never use them as sign extension.
    if len(raw) % 4:
        raise ValueError('partial IQ frame')
    low = np.frombuffer(raw, dtype='<u2') & 0xfff
    return ((low.astype(np.int32) ^ 0x800) - 0x800).astype(np.int16).reshape(-1, 2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--iq-archive', type=Path, required=True)
    parser.add_argument('--fb-snapshot', type=Path, required=True)
    parser.add_argument('--fb-archive', type=Path, required=True)
    args = parser.parse_args()
    capture = read_report(args.capture)
    metadata = capture['native_metadata']
    iq_archive, raw = archive_bytes(args.iq_archive)
    fb_archive, fb_raw = archive_bytes(args.fb_archive)
    snapshot = read_report(args.fb_snapshot)
    boot = capture['expected_boot']
    if any(r['expected_boot'] != boot for r in (iq_archive, fb_archive, snapshot)):
        raise ValueError('mixed boot evidence')
    if (metadata['status'] != 'pass' or not metadata['scan_layout_validated']
            or not metadata['complete_returned_buffers_saved']
            or not capture['independent_final_idle_verified']
            or metadata['source_format'] != 'le:S12/16>>0'
            or metadata['frame_bytes'] != 4
            or metadata['channels'] != ['voltage0:I', 'voltage1:Q']
            or len(raw) != capture['raw_bytes'] or sha(raw) != capture['raw_sha256']
            or len(raw) != metadata['raw_file_bytes_written']):
        raise ValueError('RX capture contract differs')
    frames = metadata['frames_per_buffer']
    blocks = metadata['completed_blocks']
    iq = decode_rx12(raw)
    if iq.shape != (frames * blocks, 2):
        raise ValueError('frame count mismatch')
    rows = []
    for index, chunk in enumerate(iq.reshape(blocks, frames, 2)):
        t = metadata['timestamps'][index]
        if (t['block_index'] != index or t['file_byte_offset'] != index * frames * 4
                or t['refill_bytes'] != frames * 4 or not t['copy_complete']):
            raise ValueError('metadata block/file mapping changed')
        power = np.mean(np.sum(chunk.astype(np.float64) ** 2, axis=1))
        rows.append(dict(index=index, rms_per_component=float(np.sqrt(power / 2)),
                         min_IQ=chunk.min(axis=0).tolist(), max_IQ=chunk.max(axis=0).tolist(),
                         raw_sha256=sha(raw[index*frames*4:(index+1)*frames*4])))
    geometry = snapshot['native_snapshot']
    if (snapshot['status'] != 'visible_framebuffer_bytes_saved_and_gzip_verified_board_side'
            or not geometry['geometry_unchanged'] or geometry['visible'] != [800, 480]
            or geometry['bpp'] != 32 or geometry['output_stride_bytes'] != 3200
            or geometry['storage'] != 'little_endian_BGRA_or_BGRX'
            or geometry['red'] != dict(offset=16, length=8, msb_right=0)
            or geometry['green'] != dict(offset=8, length=8, msb_right=0)
            or geometry['blue'] != dict(offset=0, length=8, msb_right=0)
            or sha(fb_raw) != snapshot['raw_sha256'] or len(fb_raw) != 800 * 480 * 4):
        raise ValueError('framebuffer contract differs')
    out = ROOT / 'results' / datetime.now(timezone.utc).strftime('p37-archive-review-%Y%m%dT%H%M%SZ')
    out.mkdir(exist_ok=False)
    Image.frombytes('RGB', (800, 480), fb_raw, 'raw', 'BGRX').save(out / 'screen.png')
    report = dict(schema='rfsig.p37_archive_review.v1',
                  status='passed_complete_saved_bytes_and_layout_only',
                  created_utc=datetime.now(timezone.utc).isoformat(), boot_id=boot,
                  evidence={k: dict(path=str(v.resolve()), sha256=sha(v.read_bytes()))
                            for k, v in vars(args).items()},
                  board_operations=False, raw_bytes=len(raw), raw_sha256=sha(raw),
                  frames=len(iq), blocks=blocks, frames_per_block=frames,
                  decode='mask low12 then sign extend; high4 ignored',
                  decoded_range=[int(iq.min()), int(iq.max())],
                  occupied_decoded_values=int(np.unique(iq).size),
                  sample_rate_hz=metadata['sample_rate_hz'],
                  frames_divided_by_rate_s=len(iq) / metadata['sample_rate_hz'],
                  duration_is_not_verified_elapsed_ADC_timeline=True,
                  block_statistics=rows, all_returned_buffers_archived=True,
                  hardware_gaps='unknown', lossless_proven=False,
                  known_target_proven=False, RF_power_dBm_calibrated=False,
                  screen_png=str((out / 'screen.png').resolve()),
                  screen_png_sha256=sha((out / 'screen.png').read_bytes()),
                  framebuffer_not_physical_panel_photo=True,
                  physical_visibility_not_inferred_from_framebuffer=True)
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    (out / 'executed.py').write_bytes(Path(__file__).read_bytes())
    print(out)
    print(report['status'])
    print(json.dumps({key: report[key] for key in ('frames', 'blocks', 'decoded_range')}))


if __name__ == '__main__':
    main()
