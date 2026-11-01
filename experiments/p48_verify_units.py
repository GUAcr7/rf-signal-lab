"""Check displayed frequency units against archived IQ and exact glyph pixels."""
import argparse
from datetime import datetime,timezone
import hashlib,json,re
from pathlib import Path
import numpy as np
from p32_session import ROOT
from p37_review_archives import archive_bytes


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text('utf-8'))


def validated_sample_rate(trial):
    """Finite and autonomous records both require verified RF readbacks."""
    from p36_full_rx_run import RF_EXPECTED
    before=trial.get('before',trial.get('armed_state',{}))
    after=trial.get('after',{})
    if before.get('attributes')!=RF_EXPECTED or after.get('attributes')!=RF_EXPECTED:
        raise ValueError('matching verified pre/post RF attributes required')
    return float(before['attributes']['in_voltage_sampling_frequency'])


def glyph_mask(label,font_path):
    rows=re.findall(r'\{\s*((?:0x[0-9a-fA-F]{2}\s*,?\s*)+)\}',font_path.read_text('ascii'))
    data=np.array([[int(v,16) for v in re.findall(r'0x([0-9a-fA-F]{2})',row)] for row in rows],dtype=np.uint8)
    if data.shape!=(95,12):raise ValueError('font shape differs')
    if any(not 32<=ord(ch)<=126 for ch in label):raise ValueError('non-ASCII label')
    return np.hstack([np.unpackbits(data[ord(ch)-32][:,None],axis=1).astype(bool) for ch in label])


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--trial',type=Path,required=True);p.add_argument('--review',type=Path,required=True);args=p.parse_args()
    trial=read(args.trial);review=read(args.review)
    if (trial['status']!='passed_long_running_RX_LCD_progress_and_independent_idle' or trial['display_revision']!='p48'
        or review['status']!='passed_P42_archives_and_independent_NumPy' or review['trial_sha256']!=sha(args.trial)):
        raise ValueError('complete P48 capture and independent review required')
    final=read(Path(review['final_review']))
    if not all(final['checks'].values()):raise ValueError('NumPy check failed')
    m=trial['frame_metrics'][-1];fs=validated_sample_rate(trial)
    expected_hz=final['NumPy_reference']['peak_offset_bins']*fs/1024
    if m['sample_rate_hz']!=fs or m['fft_bin_width_hz']!=fs/1024 or m['peak_offset_hz']!=expected_hz:raise ValueError('frequency conversion differs')
    entry=next(v for v in review['stages'] if v['label']=='framebuffer_archive');archive_path=Path(entry['report'])
    if sha(archive_path)!=entry['report_sha256']:raise ValueError('pixel archive report changed')
    _,pixels=archive_bytes(archive_path);image=np.frombuffer(pixels,dtype='<u4').reshape(480,800)
    font=ROOT/'embedded/arm_panel/font8x12.h'
    labels=[('peak_offset',f'{expected_hz/1000:+.1f} kHz',250,338),
            ('sample_rate',f'{fs/1e6:.3f} MS/s',250,392),('FFT_spacing',f'{fs/1024/1000:.1f} kHz',250,428)]
    checks={};values={}
    for name,label,x,y in labels:
        mask=glyph_mask(label,font);expected=np.where(mask,0xffdee6ee,0xff0c0e12).astype('<u4')
        checks[name+'_pixels_exact']=bool(np.array_equal(image[y:y+12,x:x+mask.shape[1]],expected));values[name]=label
    if not all(checks.values()):raise ValueError('displayed text differs from native/NumPy units')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p48-unit-review-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    report=dict(status='passed_P48_frequency_units_and_exact_framebuffer_glyphs',trial=str(args.trial.resolve()),trial_sha256=sha(args.trial),
        review=str(args.review.resolve()),review_sha256=sha(args.review),checks=checks,displayed=values,
        sample_rate_hz=fs,peak_offset_hz=expected_hz,FFT_bin_spacing_hz=fs/1024,font_sha256=sha(font),
        board_operations=False,physical_screen_confirmation=False,absolute_RF_frequency_calibrated=False,AI_inference=False)
    (out/'executed.py').write_bytes(Path(__file__).read_bytes());(out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(out);print(report['status'])


if __name__=='__main__':main()
