"""Build an isolated factory RF candidate changing ONLY two DMA resource sizes."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from p30_display_profile import properties
from p32_session import ROOT


def main():
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p32-dma-trial-build-%Y%m%dT%H%M%SZ')
    out.mkdir(exist_ok=False)
    original=ROOT/'results/p31-board-contract-20261019T135528Z/factory-rf.dtbo'
    expected='434855ac7488369a4a782c2f6be5c742e4ea62861773d3b671d0792e971e139f'
    if hashlib.sha256(original.read_bytes()).hexdigest()!=expected:raise RuntimeError('factory blob changed')
    tools=Path(json.loads((ROOT/'results/p31-dtc-active.json').read_text('utf-8'))['bin'])
    report=dict(status='building',stages=[],checks=[],hardware_access=False,original_sha256=expected)
    def save(): (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    def run(name,args):
        r=subprocess.run([str(a) for a in args],capture_output=True,timeout=25)
        (out/(name+'.stdout')).write_bytes(r.stdout);(out/(name+'.stderr')).write_bytes(r.stderr)
        report['stages'].append(dict(name=name,command=[str(a) for a in args],exit_code=r.returncode));save()
        if r.returncode:raise RuntimeError(name+' failed')
    def check(name,ok):
        report['checks'].append(dict(name=name,passed=bool(ok)))
        if not ok:raise RuntimeError(name)
    try:
        source=out/'factory-rf.dts'
        run('decompile',[tools/'dtc.exe','-I','dtb','-O','dts','-o',source,original])
        text=source.read_text('utf-8')
        for addr in ['7c400000','7c420000']:
            before=f'reg = <0x{addr} 0x10000>;'
            check('unique source resource '+addr,text.count(before)==1)
            text=text.replace(before,f'reg = <0x{addr} 0x1000>;')
        candidate=out/'factory-rf-dma4k.dts'
        candidate.write_text(text,encoding='utf-8',newline='\n')
        blob=out/'factory-rf-dma4k.dtbo'
        run('compile',[tools/'dtc.exe','-I','dts','-O','dtb','-o',blob,candidate])
        old=properties(original.read_bytes());new=properties(blob.read_bytes())
        check('property key set unchanged',old.keys()==new.keys())
        changed={k for k in old if old[k]['hex']!=new[k]['hex']}
        allowed={k for k in old if any(k.endswith('/dma@'+a+'/reg') for a in ['7c400000','7c420000'])}
        check('exactly two resource values changed',changed==allowed and len(changed)==2)
        for k in allowed:
            check('resource now 4096 '+k,new[k]['u32']==[old[k]['u32'][0],4096])
        check('no firmware request added',not any(k.endswith('/firmware-name') for k in new))
        report.update(status='factory_resource_only_candidate_verified',dtbo=str(blob),
            candidate_sha256=hashlib.sha256(blob.read_bytes()).hexdigest(),changes=sorted(changed),
            scope='Original factory RF PL and clocks only; not merged PL clock validation')
    except Exception as exc:report.update(status='failed',error=repr(exc))
    finally:save();print(out);print(report['status'])
    return 0 if report['status'].endswith('_verified') else 1


if __name__=='__main__':raise SystemExit(main())
