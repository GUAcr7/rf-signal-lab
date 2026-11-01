"""Portable positive, negative and relocated-package forward checks."""
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ap=argparse.ArgumentParser()
ap.add_argument('--tool-root',type=Path,required=True)
ap.add_argument('--output',type=Path,required=True)
a=ap.parse_args()
out=a.output.resolve(); out.mkdir(parents=True,exist_ok=False)
skill=Path(__file__).resolve().parent/'skill/verify-fixed-point-fir'
clone=out/'relocated skill'
shutil.copytree(skill,clone)
checks=[]
def call(label,case,*,dut=None,tool=None,passes=True):
    dest=out/label
    cmd=[sys.executable,str(clone/'scripts/verify.py'),'--case',str(case),'--output',str(dest),'--tool-root',str(tool or a.tool_root)]
    if dut: cmd+=['--dut',str(dut)]
    p=subprocess.run(cmd,cwd=out,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',timeout=150)
    (out/(label+'.log')).write_text(p.stdout,encoding='utf-8')
    r=json.loads((dest/'report.json').read_text(encoding='utf-8'))
    ok=(p.returncode==0 and r['all_passed']) if passes else (p.returncode!=0 and not r['all_passed'])
    checks.append({'name':label,'expected_pass':passes,'actual_exit':p.returncode,'passed':ok,'error':r.get('error')})
    if not ok: raise AssertionError(label)
    return dest,r
try:
    for name in ['three-tap','five-tap','nineteen-tap-saturation']:
        dest,r=call(name,clone/'examples'/f'{name}.json')
        vectors=json.loads((dest/'vectors.json').read_text())
        d=vectors['case']; iq=d['samples_iq']; coeff=d['coefficients_q17']
        for n,row in enumerate(vectors['expected_iq']):
            for ch in [0,1]:
                exact=sum((Fraction(c*iq[n-k][ch],131072) for k,c in enumerate(coeff) if 0<=n-k<len(iq)),Fraction())
                nearest=round(exact)
                assert row[ch]==max(-32768,min(32767,nearest))
                assert vectors['saturation_iq'][n][ch]==int(not -32768<=nearest<=32767)
        checks.append({'name':name+' independent Fraction oracle','passed':True,'output_pairs':len(vectors['expected_iq']),'saturated_components':r['reference_saturated_components']})
        if name=='nineteen-tap-saturation':
            assert r['reference_saturated_components']>0
    mutated=out/'wrong-dut.v'
    original=(clone/'assets/fixed_fir_iq.v').read_text(encoding='utf-8')
    assert 'm_q <= converted_q[15:0];' in original
    mutated.write_text(original.replace('m_q <= converted_q[15:0];','m_q <= converted_i[15:0];'),encoding='utf-8')
    call('reject-wrong-channel',clone/'examples/three-tap.json',dut=mutated,passes=False)
    wrongflag=out/'wrong-saturation.v'
    assert 'm_sat_i <= converted_i[16];' in original
    wrongflag.write_text(original.replace('m_sat_i <= converted_i[16];',"m_sat_i <= 1'b0;"),encoding='utf-8')
    call('reject-missing-saturation',clone/'examples/nineteen-tap-saturation.json',dut=wrongflag,passes=False)
    for label,value in [('reject-out-of-range',2048),('reject-bool',True)]:
        bad=json.loads((clone/'examples/three-tap.json').read_text()); bad['samples_iq'][0][0]=value
        p=out/(label+'.json'); p.write_text(json.dumps(bad),encoding='utf-8')
        call(label,p,passes=False)
    call('reject-missing-tool',clone/'examples/three-tap.json',tool=out/'no-such-tool',passes=False)
    summary={'all_passed':all(c['passed'] for c in checks),'checks':checks,'relocated_package':str(clone),
             'scope':'three FIR configurations + Fraction oracle + channel/saturation DUT defects + invalid input + absent tool',
             'board_accessed':False,'cross_board_verified':False,'PYNQ_verified':False}
except Exception as e:
    summary={'all_passed':False,'checks':checks,'error':str(e)}
(out/'validation-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False))
sys.exit(0 if summary['all_passed'] else 1)
