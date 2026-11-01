"""Offline publication checks with independent numerical expectations; no hardware."""
from pathlib import Path
from fractions import Fraction
import ast,hashlib,importlib.util,json,sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))

def main():
    report={'hardware_accessed':False,'rtl_simulation_rerun':False,'checks':[]}
    manifest=json.loads((ROOT/'package_manifest.json').read_text(encoding='utf8'))
    for row in manifest['files']:
        p=(ROOT/row['path']).resolve()
        assert p.is_relative_to(ROOT) and p.is_file(),row['path']
        assert p.stat().st_size==row['bytes'],row['path']
        assert hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256'],row['path']
    report['checks'].append({'name':'published_file_hashes','files':len(manifest['files']),'passed':True})
    parsed=0
    for folder in ['src','host','embedded','experiments','tests','build','sim','skill']:
        for p in (ROOT/folder).rglob('*.py'):
            ast.parse(p.read_text(encoding='utf-8-sig'),filename=str(p));parsed+=1
    report['checks'].append({'name':'active_python_syntax','files':parsed,'passed':True})

    import numpy as np
    from rfsig.fixed_fir import apply_fixed_fir_full,quantize_accumulator
    total=0;saturations=0
    for p in sorted((ROOT/'skill/verify-fixed-point-fir/examples').glob('*.json')):
        case=json.loads(p.read_text(encoding='utf8'));iq=case['samples_iq'];taps=case['coefficients_q17']
        result=apply_fixed_fir_full(iq,taps)
        for n,row in enumerate(result.counts):
            for ch in [0,1]:
                exact=sum((Fraction(c*iq[n-k][ch],131072) for k,c in enumerate(taps) if 0<=n-k<len(iq)),Fraction())
                rounded=round(exact);clipped=max(-32768,min(32767,rounded))
                assert int(row[ch])==clipped,(p.name,n,ch)
                assert bool(result.saturated[n,ch])==(rounded!=clipped)
                saturations+=int(rounded!=clipped)
            total+=1
    assert saturations>0
    for value in [-(1<<35),-4295032833,-196608,-65536,0,65536,196608,(1<<35)-1]:
        expected=round(Fraction(value,131072));q,s=quantize_accumulator(value)
        assert q==max(-32768,min(32767,expected)) and s==(q!=expected)
    for invalid in [True,1.5,1<<35]:
        try:quantize_accumulator(invalid)
        except ValueError:pass
        else:raise AssertionError('Invalid accumulator accepted')
    report['checks'].append({'name':'fir_fraction_oracle_and_boundaries','output_pairs':total,'saturated_components':saturations,'passed':True})

    kit=ROOT/'data/rf-learning-kit'
    spec=importlib.util.spec_from_file_location('published_rf_data_api',kit/'data_api.py')
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    _,records=module.load_kit(kit)
    assert set(records)=={'tone','bpsk','qpsk','qam16'}
    report['checks'].append({'name':'original_rx12_and_npz_identity','waveforms':4,'dma_blocks':16,'complex_samples':1048576,'passed':True})
    report['all_passed']=True
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
