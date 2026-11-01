"""Independent known-RF AI/plots plus P69 metric history, numbers and glyphs."""
import argparse,json,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
from PIL import Image
from p45_checkpoint import ROOT,read,write,sha,rel
from p37_review_archives import decode_rx12
from p48_verify_units import glyph_mask
from rfsig.spectrum import welch_power_spectrum
from rfsig.bandwidth import occupied_bandwidth

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--trial',required=True,type=Path);a=ap.parse_args();t=read(a.trial)
    if t['status']!='passed_P69_RF_dashboard_300s_archived_pending_independent_review':raise ValueError('complete trial required')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p69-board-review-%Y%m%dT%H%M%SZ');out.mkdir()
    r=dict(status='reviewing',trial=rel(a.trial),trial_sha256=sha(a.trial),board_operations=False,gates=[],shots=[],
        independent_AI_accuracy=False,physical_numeric_visibility='not_observed_during_signal_by_user')
    def check(name,ok):
        r['gates'].append(dict(name=name,passed=bool(ok)))
        if not ok:raise ValueError(name)
    try:
        parent=ROOT/'experiments/p68_review_rf.py'
        manifest=read(ROOT/'results/p68-final-20261026T023906Z/manifest.json')
        check('frozen P68 reviewer',sha(parent)==manifest['files'][rel(parent)]['sha256'])
        text=parent.read_text(encoding='utf-8').replace('P68','P69').replace("summary['display_revision']=='p67'","summary['display_revision']=='p69'")
        text=text.replace("strftime('p68-review-","strftime('p69-base-review-")
        prefix='import sys\nsys.path[:0] = '+repr([str(ROOT/'experiments'),str(ROOT/'src')])+'\n'
        code=out/'base-review.py';code.write_text(prefix+text,encoding='utf-8')
        q=subprocess.run([sys.executable,str(code),'--trial',str(a.trial)],cwd=ROOT,capture_output=True,timeout=180)
        (out/'base.stdout').write_bytes(q.stdout);(out/'base.stderr').write_bytes(q.stderr)
        reports=[Path(line.strip())/'report.json' for line in q.stdout.decode(errors='replace').splitlines() if line.startswith(str(ROOT))]
        check('AI full history/Python/plots',q.returncode==0 and len(reports)==1)
        base=read(reports[0]);r.update(base_review=rel(reports[0]),base_review_sha256=sha(reports[0]))
        files=a.trial.parent/'files';rows=[json.loads(s) for s in (files/'metrics-history.jsonl').read_text().splitlines()]
        ai=[json.loads(s) for s in (files/'ai-history.jsonl').read_text().splitlines()]
        check('one measurement per AI update and stop',len(rows)==len(ai))
        fields=('center_offset_hz','LO_plus_center_hz','ROI_99_width_hz','ROI_power_counts_squared','background_ROI_power','power_ratio')
        for m,d in zip(rows,ai):
            if (m['source_block_sequence']!=d['source_block_sequence'] or m['AI_state']!=d['state']
                or m['accepted_class']!=d['accepted_class'] or m['calibration_token']!=d['calibration_token']):raise ValueError('measurement block/policy binding')
            if m['valid']:
                if (d['state'] not in ('UNSUPPORTED_TONE','CLASSIFIED','UNCERTAIN') or not d['ready']
                    or m['power_ratio']<10 or any(m[k] is None or not np.isfinite(m[k]) for k in fields)):raise ValueError('invalid validity gate')
                if not np.isclose(m['ROI_power_counts_squared']/m['background_ROI_power'],m['power_ratio'],rtol=1e-12):raise ValueError('ROI power ratio')
            elif any(m[k] is not None for k in fields):raise ValueError('stale invalid number')
        final=read(files/'metrics.json')
        check('final values cleared',final==rows[-1] and not final['valid'] and final['measurement_status']=='STOPPED')
        def pixels(path,m):
            p=np.fromfile(path,dtype='<u4').reshape(480,800)
            labels=[(286,'State: '+m['measurement_status'],0xffdee6ee)]
            if m['valid']:
                labels += [(308,'LO+center '+format(m['LO_plus_center_hz']/1e6,'.3f')+' MHz',0xffdee6ee),
                    (328,'99% ROI BW '+format(m['ROI_99_width_hz']/1e3,'.1f')+' kHz',0xffdee6ee),
                    (348,'Center offset '+format(m['center_offset_hz']/1e3,'+.1f')+' kHz',0xffdee6ee),
                    (368,'ROI power '+format(m['ROI_power_counts_squared'],'.1f')+' counts^2',0xffdee6ee),
                    (388,'Above background '+format(10*np.log10(m['power_ratio']),'+.1f')+' dB',0xffdee6ee)]
            else:labels += [(308,'LO+center: unavailable',0xff96a5b6),(328,'99% ROI BW: unavailable',0xff96a5b6)]
            for y,label,colour in labels:
                mask=glyph_mask(label,ROOT/'embedded/arm_panel/font8x12.h')
                expected=np.where(mask,colour,0xff0c0e12).astype('<u4')
                check('actual metric pixels '+path.stem+' '+str(y),np.array_equal(p[y:y+12,456:456+mask.shape[1]],expected))
        for shot in t['shots']:
            name='shot-'+format(shot['id'],'02d');m=read(files/(name+'.metrics.json'));decision=read(files/(name+'.json'))
            matches=[v for v in rows if v['source_block_sequence']==m['source_block_sequence']]
            check('same-block metric snapshot '+name,len(matches)==1 and matches[0]==m and decision['source_block_sequence']==m['source_block_sequence'])
            item=dict(label=shot['label'],valid=m['valid'],status=m['measurement_status'],metrics=m)
            pair=decode_rx12((files/(name+'.bin')).read_bytes());x=pair[:,0].astype(float)+1j*pair[:,1]
            if m['valid']:
                spec=welch_power_spectrum(x[:8192],30720000,1024,overlap=0)
                center=decision['common_IF_hz'];gold=occupied_bandwidth(spec.frequency_hz,spec.psd,(center-600000,center+600000),rf_lo_hz=m['rx_LO_readback_hz'])
                width_error=abs(gold.bandwidth_hz-m['ROI_99_width_hz']);center_error=abs(gold.center_baseband_hz-m['center_offset_hz'])
                check('native/Python numbers '+name,width_error<5 and center_error<5 and abs(gold.observed_region_power-m['ROI_power_counts_squared'])<1e-4*max(1,gold.observed_region_power))
                item.update(width_numeric_error_hz=width_error,center_numeric_error_hz=center_error)
            pixels(files/(name+'.raw'),m)
            Image.frombytes('RGB',(800,480),(files/(name+'.raw')).read_bytes(),'raw','BGRX').save(out/(name+'-'+shot['label']+'.png'))
            r['shots'].append(item)
        pixels(files/'fb.raw',final)
        Image.frombytes('RGB',(800,480),(files/'fb.raw').read_bytes(),'raw','BGRX').save(out/'stopped-cleared.png')
        build=read(ROOT/t['build'])
        for p,h in build['inputs_sha256'].items():check('candidate input unchanged '+p,sha(ROOT/p)==h)
        r.update(status='passed_P69_native_ROI_RF_AI_pixels_and_invalidation',build=t['build'],build_sha256=t['build_sha256'],
            binary_sha256=build['binary_sha256'],display_updates=len(ai)-1,duration_software_s=base['duration_software_s'],
            valid_measurements=sum(v['valid'] for v in rows),invalid_measurements=sum(not v['valid'] for v in rows),
            metrics_on_LCD=True,absolute_RF_frequency_calibrated=False,RF_power_dbm_calibrated=False,
            background_reference_scope='four C-cached background blocks; raw reference blocks not individually archived',
            persistent_profile_changed=False)
    except Exception as e:r.update(status='failed_or_unconfirmed_P69_review',error=repr(e))
    r['files_sha256']={rel(p):sha(p) for p in out.rglob('*') if p.is_file() and p.name!='report.json'}
    write(out/'report.json',r);print(out);print(r['status']);return int(not r['status'].startswith('passed'))
if __name__=='__main__':raise SystemExit(main())
