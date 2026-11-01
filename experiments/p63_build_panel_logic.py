"""Offline panel contract tests and ARM ABI checks. No board operations."""
from datetime import datetime,timezone
import hashlib,json,re,subprocess
from pathlib import Path
from p36_build_rx_full import ROOT,TOOL,posix

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p63-panel-build-%Y%m%dT%H%M%SZ')
    out.mkdir(exist_ok=False)
    source=ROOT/'embedded/source_panel/panel_logic_check.c'
    inputs=[source,source.with_name('panel_logic.h'),ROOT/'tests/native/check_source_panel.py',
            ROOT/'src/rfsig/tjc_protocol.py',Path(__file__)]
    r=dict(status='building',board_operations=False,UART_tested=False,RF_tested=False,
           inputs_sha256={str(p.relative_to(ROOT)):sha(p) for p in inputs},stages=[])
    def save(): (out/'report.json').write_text(json.dumps(r,indent=2)+'\n')
    def run(label,args):
        p=subprocess.run([str(v) for v in args],capture_output=True,timeout=100)
        (out/(label+'.stdout')).write_bytes(p.stdout);(out/(label+'.stderr')).write_bytes(p.stderr)
        r['stages'].append(dict(label=label,exit_code=p.returncode));save()
        if p.returncode: raise RuntimeError(label+' failed')
        return p.stdout.decode(errors='replace')
    save()
    try:
        host=out/'panel-logic-host';arm=out/'panel-logic-arm'
        flags=['-std=c11','-O2','-Wall','-Wextra','-Werror']
        run('host-build',['wsl.exe','--exec','gcc',*flags,posix(source),'-o',posix(host)])
        r['selftest']=json.loads(run('selftest',['wsl.exe','--exec',posix(host),'--selftest']))
        run('contracts',['wsl.exe','--exec','python3',posix(ROOT/'tests/native/check_source_panel.py'),
                         posix(host),posix(out/'contracts')])
        r['contracts']=json.loads((out/'contracts/report.json').read_text())
        run('ARM-build',['wsl.exe','--exec',posix(TOOL/'arm-linux-gnueabihf-gcc'),*flags,
                         '-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard','-marm',posix(source),'-o',posix(arm)])
        elf=run('ARM-readelf',['wsl.exe','--exec',posix(TOOL/'arm-linux-gnueabihf-readelf'),'-h','-A','-l','-V',posix(arm)])
        versions=[tuple(map(int,v.split('.'))) for v in re.findall(r'GLIBC_([0-9.]+)',elf)]
        checks=dict(ELF32='ELF32' in elf,ARM='Machine:                           ARM' in elf,
            little_endian='little endian' in elf,hard_float='Tag_ABI_VFP_args: VFP registers' in elf,
            interpreter='/lib/ld-linux-armhf.so.3' in elf,glibc_compatible=bool(versions) and max(versions)<=(2,28),
            sources_unchanged=all(sha(ROOT/p)==s for p,s in r['inputs_sha256'].items()))
        if not all(checks.values()):raise ValueError('ABI or source changed')
        r.update(status='passed_P63_offline_contract_and_ARM_build_not_hardware',checks=checks,
                 ARM_binary=str(arm.relative_to(ROOT)),ARM_sha256=sha(arm))
        for p in inputs:
            target=out/'inputs'/p.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(p.read_bytes())
    except Exception as e:r.update(status='failed_or_incomplete',error=repr(e))
    save();print(out/'report.json');print(r['status'])
    return 0 if r['status'].startswith('passed_') else 1

if __name__=='__main__': raise SystemExit(main())
