"""Build explicit internal-UART checker; refusal and ARM ABI checks, no board IO."""
from datetime import datetime,timezone
import json,re,subprocess
from p36_build_rx_full import ROOT,TOOL,posix,sha
def main():
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p64-internal-build-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    src=ROOT/'embedded/p201_uart/uart_internal_check.c';arm=out/'uart-internal-arm';host=out/'uart-internal-host'
    r=dict(status='building',board_operations=False,source_sha256=sha(src),stages=[])
    def save():(out/'report.json').write_text(json.dumps(r,indent=2)+'\n')
    def run(label,args,expected=0):
        p=subprocess.run([str(v) for v in args],capture_output=True,timeout=90)
        (out/(label+'.stdout')).write_bytes(p.stdout);(out/(label+'.stderr')).write_bytes(p.stderr)
        r['stages'].append(dict(label=label,exit_code=p.returncode,expected=expected));save()
        if p.returncode!=expected:raise ValueError(label+' failed')
        return p.stdout.decode(errors='replace')
    save()
    try:
        flags=['-std=c11','-O2','-Wall','-Wextra','-Werror']
        run('host-build',['wsl.exe','--exec','gcc',*flags,posix(src),'-o',posix(host)])
        for name,args in [('missing',[]),('console',['--device','/dev/ttyPS0','--run-internal']),
                          ('PTY',['--device','/dev/pts/1','--run-internal']),
                          ('wrong_identity',['--device','/dev/ttyPS1','--run-internal'])]:
            run(name,['wsl.exe','--exec',posix(host),*args],2)
        run('ARM-build',['wsl.exe','--exec',posix(TOOL/'arm-linux-gnueabihf-gcc'),*flags,
            '-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard','-marm',posix(src),'-o',posix(arm)])
        elf=run('ARM-readelf',['wsl.exe','--exec',posix(TOOL/'arm-linux-gnueabihf-readelf'),'-h','-A','-l','-V',posix(arm)])
        versions=[tuple(map(int,v.split('.'))) for v in re.findall(r'GLIBC_([0-9.]+)',elf)]
        checks=dict(ELF32='ELF32' in elf,ARM='Machine:                           ARM' in elf,little_endian='little endian' in elf,
            hard_float='Tag_ABI_VFP_args: VFP registers' in elf,interpreter='/lib/ld-linux-armhf.so.3' in elf,
            glibc=bool(versions) and max(versions)<=(2,28),source_unchanged=sha(src)==r['source_sha256'])
        if not all(checks.values()):raise ValueError('ABI gate failed')
        (out/src.name).write_bytes(src.read_bytes())
        r.update(status='passed_P64_internal_tool_build_refusals_not_board_test',checks=checks,
            binary=str(arm.relative_to(ROOT)),binary_sha256=sha(arm))
    except Exception as e:r.update(status='failed_or_incomplete',error=repr(e))
    save();print(out/'report.json');print(r['status'])
    return 0 if r['status'].startswith('passed_') else 1
if __name__=='__main__':raise SystemExit(main())
