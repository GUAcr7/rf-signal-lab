"""Build standalone native candidate; verify original validation and exposed IQ.

No serial/board access, no independent P52 test read, no production changes.
"""
import argparse, subprocess
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from p45_checkpoint import ROOT, read, write, sha, rel
from p36_build_rx_full import TOOL, posix
from p74_phase_pool import phase_pool_logits
from rfsig.trainable_cnn import preprocess, patches
from rfsig.cnn_quantization import quantized_forward
from p37_review_archives import decode_rx12
from rfsig.rf_ai_calibration import adapt_calibrated


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--offline',required=True,type=Path)
    a=ap.parse_args();proof=read(a.offline)
    if proof['status']!='passed_P74_offline_candidate_requires_native_parity_fresh_RF':
        raise ValueError('passed validation and exposed event gates required')
    if sha(ROOT/'experiments/p74_phase_pool.py')!=proof['protocol']['candidate_sha256']:
        raise ValueError('candidate changed after offline selection')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p74-native-%Y%m%dT%H%M%SZ');out.mkdir()
    bundle=out/'bundle';bundle.mkdir()
    frozen=read(ROOT/'results/p52-export-20261024T043113Z/report.json')
    for item in frozen['frozen_inputs'].values():
        if sha(ROOT/item['path'])!=item['sha256']:raise ValueError('frozen input changed')
    for key in ('C','header'):
        src=ROOT/frozen['frozen_inputs'][key]['path'];(bundle/src.name).write_bytes(src.read_bytes())
    for name in ('phase_pool.h','phase_cli.c'):
        src=ROOT/'embedded/arm_live_panel_p74'/name;(bundle/name).write_bytes(src.read_bytes())
    r=dict(status='building_P74_standalone',offline=rel(a.offline),offline_sha256=sha(a.offline),
           board_operations=False,production_changed=False,stages=[],checks=[])
    def run(label,argv):
        child=subprocess.run([str(x) for x in argv],capture_output=True,timeout=90)
        (out/(label+'.stdout')).write_bytes(child.stdout);(out/(label+'.stderr')).write_bytes(child.stderr)
        r['stages'].append(dict(label=label,exit_code=child.returncode));write(out/'report.json',r)
        if child.returncode:raise ValueError(label+' failed')
        return child
    def fixture(name,frames,quantized):
        frames=np.asarray(frames,dtype=np.complex64)
        raw=out/(name+'.f32');interleaved=np.stack((frames.real,frames.imag),axis=-1)
        raw.write_bytes(interleaved.astype('<f4').tobytes())
        all_modes={}
        for mode in ('baseline','pool'):
            expected=(phase_pool_logits(frames,quantized) if mode=='pool' else
                      quantized_forward(patches(preprocess(frames)),quantized))
            actual=run(name+'-'+mode,['wsl.exe','--exec',posix(out/'phase-host'),posix(raw),mode])
            rows=np.array([np.fromstring(s,sep=',') for s in actual.stdout.decode().splitlines()])
            if rows.shape!=(len(frames),5) or not np.isfinite(rows).all():raise ValueError('malformed C rows')
            np.testing.assert_array_equal(rows[:,0],np.arange(len(frames)))
            np.testing.assert_allclose(rows[:,1:4],expected,rtol=1e-4,atol=5e-4)
            np.testing.assert_array_equal(rows[:,4],expected.argmax(axis=1))
            all_modes[mode]=dict(expected_logits=expected.tolist(),predictions=rows[:,4].astype(int).tolist(),
                                 max_logit_error=float(abs(rows[:,1:4]-expected).max()))
        r['checks'].append(dict(name=name,path=rel(raw),sha256=sha(raw),frames=len(frames),modes=all_modes))
        write(out/'report.json',r)
    try:
        flags=['-std=c11','-O2','-Wall','-Wextra','-Werror','-fno-fast-math','-ffp-contract=off']
        for label,cc in [('host','gcc'),('ARM',posix(TOOL/'arm-linux-gnueabihf-gcc'))]:
            cpu=[] if label=='host' else ['-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard','-marm']
            run(label+'-build',['wsl.exe','--exec',cc,*flags,*cpu,posix(bundle/'phase_cli.c'),'-o',posix(out/('phase-'+label)),'-lm'])
        with np.load(ROOT/frozen['frozen_inputs']['quantized']['path'],allow_pickle=False) as z:q=dict(z)
        with np.load(ROOT/'results/p54-plan-20261024T042837Z/dataset/frames.npz',allow_pickle=False) as z:
            validation=z['frames'][z['split']=='validation']
        fixture('validation',validation,q)
        # Independently exercise finite phase rotations and amplitude/DC controls.
        controlled=np.concatenate([validation[0:1]*np.exp(1j*np.deg2rad(d)) for d in range(0,360,45)]
                                  +[validation[0:1]*4+(3+2j)])
        fixture('controlled-rotations',controlled,q)
        review=read(ROOT/proof['review']);trial_path=ROOT/review['trial'];trial=read(trial_path)
        if sha(trial_path)!=review['trial_sha256']:raise ValueError('P73 trial changed')
        files=trial_path.parent/'files'
        for e in trial['events']:
            base=f'event-{e["id"]:02d}';ai=read(files/(base+'.json'));raw=files/(base+'.bin')
            if sha(raw)!=trial['files_sha256'][raw.name]:raise ValueError('event IQ changed')
            pairs=decode_rx12(raw.read_bytes());iq=pairs[:,0].astype(float)+1j*pairs[:,1]
            cal=dict(status='known_tone_common_IF_calibrated',frequency_hz=ai['common_IF_hz'],
                     shared_across_modulation_classes=True,modulation_labels_used=False)
            frames,_=adapt_calibrated(iq,sample_rate_hz=30720000,calibration=cal)
            fixture(base,frames,q)
        for name,data in [('empty',b''),('short',bytes(5)),('zero',bytes(8192)),
                          ('nan',np.full(2048,np.nan,dtype='<f4').tobytes())]:
            raw=out/(name+'.f32');raw.write_bytes(data)
            child=subprocess.run(['wsl.exe','--exec',posix(out/'phase-host'),posix(raw),'pool'],capture_output=True,timeout=10)
            r['checks'].append(dict(name='reject-'+name,exit_code=child.returncode))
            if child.returncode!=2:raise ValueError('bad input not rejected')
        r.update(status='passed_P74_native_host_Python_parity_ARM_crossbuild_pending_execution',
                 total_parity_frames=sum(x.get('frames',0) for x in r['checks']),
                 ARM_binary=rel(out/'phase-ARM'),ARM_binary_sha256=sha(out/'phase-ARM'),
                 host_binary=rel(out/'phase-host'),host_binary_sha256=sha(out/'phase-host'),
                 inputs_sha256={rel(p):sha(p) for p in [Path(__file__),ROOT/'experiments/p74_phase_pool.py',*bundle.iterdir()]})
    except Exception as exc:r.update(status='failed_P74_native_verification',error=repr(exc))
    write(out/'report.json',r);print(out);print(r['status'])


if __name__=='__main__':main()
