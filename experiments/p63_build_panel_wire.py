"""Offline native wire parser differential check and ARM build; no board IO."""
from datetime import datetime,timezone
import json,re,subprocess
from pathlib import Path
from p36_build_rx_full import ROOT,TOOL,posix,sha

def main():
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p63-wire-build-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    source=ROOT/'embedded/source_panel/panel_wire_check.c'
    inputs=[source,source.with_name('panel_wire.h'),ROOT/'tests/native/check_panel_wire.py',
            ROOT/'src/rfsig/tjc_protocol.py',Path(__file__)]
    r=dict(status='building',board_operations=False,inputs_sha256={str(p.relative_to(ROOT)):sha(p) for p in inputs},stages=[])
    def save():(out/'report.json').write_text(json.dumps(r,indent=2)+'\n')
    def run(label,args):
        p=subprocess.run([str(v) for v in args],capture_output=True,timeout=100)
        (out/(label+'.stdout')).write_bytes(p.stdout);(out/(label+'.stderr')).write_bytes(p.stderr)
        r['stages'].append(dict(label=label,exit_code=p.returncode));save()
        if p.returncode:raise RuntimeError(label+' failed')
        return p.stdout.decode(errors='replace')
    save()
    try:
        host=out/'wire-host';arm=out/'wire-arm';flags=['-std=c11','-O2','-Wall','-Wextra','-Werror']
        run('host-build',['wsl.exe','--exec','gcc',*flags,posix(source),'-o',posix(host)])
        r['selftest']=json.loads(run('selftest',['wsl.exe','--exec',posix(host),'--selftest']))
        run('contracts',['wsl.exe','--exec','python3',posix(ROOT/'tests/native/check_panel_wire.py'),posix(host),posix(out/'contracts')])
        r['contracts']=json.loads((out/'contracts/report.json').read_text())
        run('ARM-build',['wsl.exe','--exec',posix(TOOL/'arm-linux-gnueabihf-gcc'),*flags,
            '-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard','-marm',posix(source),'-o',posix(arm)])
        elf=run('ARM-readelf',['wsl.exe','--exec',posix(TOOL/'arm-linux-gnueabihf-readelf'),'-h','-A','-l','-V',posix(arm)])
        versions=[tuple(map(int,v.split('.'))) for v in re.findall(r'GLIBC_([0-9.]+)',elf)]
        checks=dict(ELF32='ELF32' in elf,ARM='Machine:                           ARM' in elf,little_endian='little endian' in elf,
            hard_float='Tag_ABI_VFP_args: VFP registers' in elf,interpreter='/lib/ld-linux-armhf.so.3' in elf,
            glibc_compatible=bool(versions) and max(versions)<=(2,28),
            sources_unchanged=all(sha(ROOT/p)==s for p,s in r['inputs_sha256'].items()))
        if not all(checks.values()):raise ValueError('ABI/input failed')
        r.update(status='passed_P63_native_wire_contract_and_ARM_build_not_hardware',checks=checks,
                 ARM_binary=str(arm.relative_to(ROOT)),ARM_sha256=sha(arm))
        for p in inputs:
            target=out/'inputs'/p.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(p.read_bytes())
    except Exception as e:r.update(status='failed_or_incomplete',error=repr(e))
    save();print(out/'report.json');print(r['status'])
    return 0 if r['status'].startswith('passed_') else 1

if __name__=='__main__':raise SystemExit(main())
