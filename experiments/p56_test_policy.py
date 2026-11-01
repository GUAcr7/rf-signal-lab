"""Recorded-data regression and synthetic negative controls; no board operations."""
import argparse,json,subprocess
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
from p45_checkpoint import ROOT,read,write,sha,rel
from p36_build_rx_full import posix
from p37_review_archives import archive_bytes,decode_rx12
from rfsig.rf_ai_calibration import measure_calibration_tone

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--build',type=Path,required=True);args=ap.parse_args()
    b=read(args.build)
    if not b['status'].startswith('passed_build_'):raise ValueError('build/lifecycle required')
    for k,v in b['inputs_sha256'].items():
        if sha(ROOT/k)!=v:raise ValueError('build input changed '+k)
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p56-policy-%Y%m%dT%H%M%SZ');out.mkdir()
    r=dict(status='testing',build=rel(args.build),build_sha256=sha(args.build),board_operations=False,
        scope='regression using previously exposed demo data and synthetic negatives; not independent accuracy or universal OOD validation')
    def run(label,cmd):
        q=subprocess.run([str(v) for v in cmd],capture_output=True,timeout=120)
        (out/(label+'.stdout')).write_bytes(q.stdout);(out/(label+'.stderr')).write_bytes(q.stderr)
        if q.returncode:raise ValueError(label+' failed '+str(q.returncode))
        return q.stdout.decode()
    try:
        bundle=(ROOT/b['binary']).parent/'bundle';binary=out/'policy-host'
        monitor=(bundle/'monitor.c').read_text()
        if monitor.count('int main(int argc, char **argv) {')!=1:raise ValueError('main entry differs')
        (out/'test_monitor.c').write_text(monitor.replace('int main(int argc, char **argv) {','int candidate_main(int argc, char **argv) {'),encoding='utf-8')
        run('build',['wsl.exe','--exec','gcc','-std=c11','-O2','-Wall','-Wextra','-Werror','-fno-fast-math','-ffp-contract=off','-pthread','-I',posix(out),'-I',posix(bundle),'-I',posix(ROOT/'embedded/vendor/libiio-v0.24'),posix(ROOT/'tests/native/p56_policy_harness.c'),'-o',posix(binary),'-ldl','-lrt','-lm'])
        rng=np.random.default_rng(2026102401)
        def packed(name,x):
            pair=np.column_stack([np.real(x),np.imag(x)])
            pair=np.rint(pair).clip(-2048,2047).astype('<i2');file=out/(name+'.bin');file.write_bytes(pair.tobytes());return file
        noise=packed('noise',rng.normal(0,2,65536)+1j*rng.normal(0,2,65536))
        zero=packed('zero',np.zeros(65536));clip=packed('clipped',np.full(65536,2047+0j))
        meta,raw=archive_bytes(ROOT/'results/p36-file-archive-20261024T080448Z/report.json')
        tones=[];gold=[]
        for i in range(2):
            path=out/('pilot'+str(i)+'.bin');path.write_bytes(raw[i*262144:(i+1)*262144]);tones.append(path)
            pair=decode_rx12(path.read_bytes());gold.append(measure_calibration_tone(pair[:,0]+1j*pair[:,1]))
        live=read(ROOT/'results/p53-live-20261024T080707Z/report.json');real=[]
        for c in live['cases']:
            _,raw=archive_bytes(ROOT/c['IQ']['archive']);path=out/(c['name']+'.bin');path.write_bytes(raw);real.append(path)
        mixed=out/'inconsistent.bin';raw=bytearray(real[0].read_bytes());offset=16*1024*4
        raw[offset:2*offset]=real[1].read_bytes()[offset:2*offset];mixed.write_bytes(raw)
        steps=[('absent',noise),('stale',noise),('model',noise),('valid',noise),('keep',noise),('keep',noise),('keep',noise),
            ('keep',noise),('keep',tones[0]),('keep',tones[1]),('keep',noise),('keep',zero),('keep',clip),
            *[('keep',v) for v in real],('keep',mixed),('stale',real[0]),('renew',noise)]
        manifest=out/'steps.txt';manifest.write_text(''.join(k+' '+posix(v)+'\n' for k,v in steps),encoding='ascii')
        rows=[json.loads(s) for s in run('policy',['wsl.exe','--exec',posix(binary),posix(manifest),posix(out/'control')]).splitlines() if s.startswith('{')]
        expected=['CALIBRATION_REQUIRED']*3+['REFERENCE']*3+['WAIT_PILOT']*3+['UNSUPPORTED_TONE','NO_USABLE_SIGNAL','NO_USABLE_SIGNAL','CLIPPED']+['CLASSIFIED']*3+['UNCERTAIN','CALIBRATION_REQUIRED','REFERENCE']
        r.update(rows=rows,expected_states=expected,tone_reference=gold)
        if [v['state'] for v in rows]!=expected:raise ValueError('policy state mismatch')
        if [v['accepted_class'] for v in rows[13:16]]!=[0,1,2] or any(v['accepted_class']!=-1 for i,v in enumerate(rows) if i not in (13,14,15)):raise ValueError('abstention or class gate failed')
        frequency=sum(v['frequency_hz'] for v in gold)/2
        if abs(rows[9]['common_IF_hz']-frequency)>1e-3:raise ValueError('native/Python tone calibration mismatch')
        f=read(ROOT/b['frozen']);exe=ROOT/f['frozen_inputs']['host']['path']
        for j,path in enumerate(real):
            ref=np.array([np.fromstring(s,sep=',') for s in run('reference-'+str(j),[exe,path,str(rows[9]['common_IF_hz']),'int8']).splitlines()])
            np.testing.assert_allclose(rows[13+j]['logits'],ref[:,1:4],rtol=1e-4,atol=5e-4)
            if rows[13+j]['predictions']!=ref[:,4].astype(int).tolist():raise ValueError('frozen C prediction parity failed')
        r.update(status='passed_runtime_policy_19_steps_tone_fit_and_frozen_frontend_parity',steps_verified=len(rows),
            calibration_difference_hz=rows[9]['common_IF_hz']-frequency,binary=rel(binary),binary_sha256=sha(binary),
            inputs_sha256={rel(p):sha(p) for p in [Path(__file__),ROOT/'tests/native/p56_policy_harness.c',manifest,*out.glob('*.bin')]})
    except Exception as e:r.update(status='failed_policy_not_deployed',error=repr(e))
    write(out/'report.json',r);print(out);print(r['status']);return int(not r['status'].startswith('passed'))
if __name__=='__main__':raise SystemExit(main())
