"""Standalone integer FIR golden reference + compatible RTL simulation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

SKILL = Path(__file__).resolve().parents[1]


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def integer(v, bits):
    if type(v) is not int or not -(1 << (bits-1)) <= v < (1 << (bits-1)):
        raise ValueError(f"expected signed {bits}-bit integer, got {v!r}")
    return v


def convert(acc):
    # Python divmod on the absolute value avoids signed shifts and float ties.
    q, r = divmod(abs(acc), 1 << 17)
    q += int(r > 65536 or (r == 65536 and q % 2))
    q = -q if acc < 0 else q
    return max(-32768, min(32767, q)), int(not -32768 <= q <= 32767)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--case', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--dut', type=Path, default=SKILL/'assets/fixed_fir_iq.v')
    ap.add_argument('--tool-root', type=Path)
    a = ap.parse_args()
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = {'all_passed': False, 'scope': 'integer_reference_and_RTL_simulation_only',
              'hardware_accessed': False, 'timing_closed': False, 'runs': []}
    try:
        casefile = a.case.resolve()
        d = json.loads(casefile.read_text(encoding='utf-8'))
        if not isinstance(d.get('name'), str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,60}', d['name']):
            raise ValueError('name must be an ASCII identifier of 1..60 characters')
        coeff, iq = d['coefficients_q17'], d['samples_iq']
        if not isinstance(coeff, list) or not 1 <= len(coeff) <= 63:
            raise ValueError('tap count must be 1..63')
        coeff = [integer(v, 18) for v in coeff]
        if not isinstance(iq, list) or not iq or len(iq)+len(coeff)-1 > 100000:
            raise ValueError('sample count outside supported range')
        for row in iq:
            if not isinstance(row, list) or len(row) != 2:
                raise ValueError('samples_iq must contain pairs')
            for v in row: integer(v, 12)
        expected, saturation = [], []
        for n in range(len(iq)+len(coeff)-1):
            accum = [sum(c*iq[n-k][ch] for k,c in enumerate(coeff) if 0 <= n-k < len(iq)) for ch in [0,1]]
            for v in accum: integer(v, 36)
            converted = [convert(v) for v in accum]
            expected.append([v[0] for v in converted]); saturation.append([v[1] for v in converted])
        # Independent direct boundary table: banker rounding, negative symmetry, saturation.
        for acc, ans in [(65536,(0,0)),(196608,(2,0)),(-65536,(0,0)),(-196608,(-2,0)),(1<<35,(32767,1)),(-(1<<35),(-32768,1))]:
            if convert(acc) != ans: raise AssertionError('golden conversion boundary failure')
        (out/'vectors.json').write_text(json.dumps({'case':d,'expected_iq':expected,'saturation_iq':saturation},indent=2),encoding='utf-8')
        files = {}
        def hexfile(key,values,bits):
            p=out/(key+'.hex')
            p.write_text(''.join(f'{v & ((1<<bits)-1):0{(bits+3)//4}x}\n' for v in values),encoding='ascii')
            files[key]=p
        hexfile('COEFF',coeff,18)
        for ch, keys in [(0,('I','EI','SI')),(1,('Q','EQ','SQ'))]:
            hexfile(keys[0],[r[ch] for r in iq],12)
            hexfile(keys[1],[r[ch] for r in expected],16)
            hexfile(keys[2],[r[ch] for r in saturation],1)
        dut, tb = a.dut.resolve(), SKILL/'assets/tb_fixed_fir_iq.sv'
        report.update(case=d['name'],tap_count=len(coeff),input_pairs=len(iq),output_pairs=len(expected),
                      reference_saturated_components=sum(map(sum,saturation)),
                      sources=[{'path':str(p),'sha256':digest(p)} for p in [casefile,dut,tb]],
                      vectors_sha256=digest(out/'vectors.json'))
        suffix='.exe' if os.name=='nt' else ''
        root=a.tool_root.resolve() if a.tool_root else None
        iv = str(root/'bin'/('iverilog'+suffix)) if root else shutil.which('iverilog')
        vvp = str(root/'bin'/('vvp'+suffix)) if root else shutil.which('vvp')
        if not iv or not vvp or not Path(iv).is_file() or not Path(vvp).is_file():
            raise FileNotFoundError('Icarus tools unavailable; install them or set --tool-root')
        env=os.environ.copy()
        env['PATH']=str(Path(iv).parent)+os.pathsep+env.get('PATH','')
        lib=root/'lib/ivl' if root else None
        def run(cmd,label):
            p=subprocess.run(list(map(str,cmd)),cwd=out,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                             text=True,encoding='utf-8',errors='replace',timeout=120)
            (out/(label+'.log')).write_text(p.stdout,encoding='utf-8')
            report['runs'].append({'stage':label,'tool_returncode':p.returncode,'command':list(map(str,cmd))})
            if p.returncode: raise RuntimeError(f'{label} failed, see {label}.log')
            return p.stdout
        run([iv,*(['-B',lib] if lib and lib.is_dir() else []),'-V'],'tool-version')
        for stalls in [0,1]:
            image=out/f'fir-{stalls}.vvp'
            run([iv,*(['-B',lib] if lib and lib.is_dir() else []),'-g2012','-Wall','-s','tb_fixed_fir_iq',
                 '-P',f'tb_fixed_fir_iq.N_TAPS={len(coeff)}','-P',f'tb_fixed_fir_iq.RANDOM_STALLS={stalls}',
                 '-o',image,dut,tb],f'compile-{stalls}')
            params={'CASE':d['name'],'INPUT_COUNT':len(iq),'OUTPUT_COUNT':len(expected),**files}
            text=run([vvp,*(['-M',lib] if lib and lib.is_dir() else []),image,*[f'+{k}={v}' for k,v in params.items()]],f'simulate-{stalls}')
            lines=[s for s in text.splitlines() if s.startswith('PASS case=')]
            if len(lines)!=1 or any(s in text for s in ['FATAL','ERROR','WARNING']):
                raise AssertionError('no clean TestBench PASS')
            fields=dict(re.findall(r'(\w+)=([^ ]+)',lines[0]))
            if int(fields['received'])!=len(expected) or int(fields['accepted'])!=len(expected) or int(fields['rounding_checks'])!=22:
                raise AssertionError('invalid TestBench counters')
            report.setdefault('self_checks',[]).append(fields)
        report['all_passed']=True
    except Exception as e:
        report['error']=f'{type(e).__name__}: {e}'
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'all_passed':report['all_passed'],'report':str(out/'report.json'),'error':report.get('error')},ensure_ascii=False))
    return 0 if report['all_passed'] else 1


if __name__=='__main__':
    sys.exit(main())
