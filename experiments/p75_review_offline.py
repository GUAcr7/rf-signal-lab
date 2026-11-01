"""Replay unchanged metric/policy safety cases against the phase-pool candidate."""
from datetime import datetime,timezone
from pathlib import Path
from p45_checkpoint import ROOT,read,write,sha,rel
from p53_build_live_ai import replace_once as sub


if __name__=='__main__':
    parent=ROOT/'experiments/p69_review_offline.py'
    baseline=read(ROOT/'results/p69-final-20261026T031117Z/manifest.json')['files']
    if sha(parent)!=baseline[rel(parent)]['sha256']:raise ValueError('tested P69 offline reviewer changed')
    text=parent.read_text(encoding='utf-8')
    text=text.replace('passed_P69_build_12_lifecycle_cases_not_deployed','passed_P75_phase_candidate_build_lifecycle12_not_deployed')
    text=text.replace("strftime('p69-offline-","strftime('p75-offline-")
    text=text.replace('passed_P69_math15_integrated14_states_shots_policy19','passed_P75_integrated14_states_shots_policy19')
    text=text.replace('failed_P69_offline_not_deployed','failed_P75_offline_not_deployed')
    text=sub(text,"        if q.returncode or policy!=read(source/'report.json')['rows']:raise ValueError('frozen policy changed')",'''        original=read(source/'report.json')['rows']
        # Logits intentionally change under the new inference; all other policy
        # fields must still be identical on these fixed safety fixtures.
        strip=lambda row:{k:v for k,v in row.items() if k!='logits'}
        if q.returncode or [strip(x) for x in policy]!=[strip(x) for x in original]:raise ValueError('policy invariants changed')
        from p74_phase_pool import phase_pool_logits
        from rfsig.rf_ai_calibration import adapt_calibrated
        frozen=read(ROOT/b['frozen'])
        with np.load(ROOT/frozen['frozen_inputs']['quantized']['path'],allow_pickle=False) as z:quant=dict(z)
        policy_paths=[line.split(' ',1)[1] for line in (source/'steps.txt').read_text().splitlines()]
        checked=0
        for item,remote in zip(policy,policy_paths):
            if min(item['predictions'])<0:continue
            # This is an original P56 fixture, decoded from its packed I/Q.
            local=Path(remote.replace('/mnt/c/','C:/',1))
            pair=decode_rx12(local.read_bytes());iq=pair[:,0].astype(float)+1j*pair[:,1]
            cal=dict(status='known_tone_common_IF_calibrated',frequency_hz=item['common_IF_hz'],shared_across_modulation_classes=True,modulation_labels_used=False)
            frames,_=adapt_calibrated(iq,sample_rate_hz=30720000,calibration=cal)
            expected_logits=phase_pool_logits(np.asarray(frames,dtype=np.complex64),quant)
            np.testing.assert_allclose(item['logits'],expected_logits,rtol=1e-4,atol=5e-4)
            np.testing.assert_array_equal(item['predictions'],expected_logits.argmax(axis=1))
            checked+=1
        r.update(policy_invariants_match=True,policy_rows=policy,new_logits_independent_Python_cases=checked)
''')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p75-offline-code-%Y%m%dT%H%M%SZ');out.mkdir()
    path=out/'executed-review.py';path.write_text(text,encoding='utf-8')
    write(out/'report.json',dict(parent=rel(parent),parent_sha256=sha(parent),code=rel(path),code_sha256=sha(path)))
    exec(compile(text,str(path),'exec'),dict(__name__='__main__',__file__=str(path)))
