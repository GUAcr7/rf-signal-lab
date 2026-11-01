"""Cross-build bounded UART check; Linux PTY and refusal tests, no hardware."""
from datetime import datetime,timezone
import hashlib,json,re,subprocess
from pathlib import Path
from p36_build_rx_full import ROOT,TOOL,posix

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p201-uart-tool-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    source=ROOT/'embedded/p201_uart/uart_loopback.c';test=ROOT/'tests/native/check_p201_uart_pty.py'
    hashes={str(p.relative_to(ROOT)):sha(p) for p in (source,test,Path(__file__))}
    r=dict(status='building',board_operations=False,physical_UART_tested=False,stages=[],inputs_sha256=hashes)
    def save():(out/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    def run(label,args):
        completed=subprocess.run([str(a) for a in args],capture_output=True,timeout=90)
        (out/(label+'.stdout')).write_bytes(completed.stdout);(out/(label+'.stderr')).write_bytes(completed.stderr)
        r['stages'].append(dict(label=label,exit_code=completed.returncode));save()
        if completed.returncode:raise RuntimeError(label+' failed')
        return completed.stdout.decode(errors='replace')
    save()
    try:
        run('linux-pty',['wsl.exe','--exec','python3',posix(test),posix(out/'pty')])
        cases=json.loads((out/'pty/pty-tests.json').read_text())['cases']
        if len(cases)!=7 or any(v['exit_code']!=v['expected'] for v in cases):raise ValueError('PTY tests incomplete')
        run('host-production-compile',['wsl.exe','--exec','gcc','-std=c11','-O2','-Wall','-Wextra','-Werror',posix(source),'-o',posix(out/'uart-host-production')])
        # Production executable must reject host-test override and console before opening.
        refusals=[]
        for name,args in [('test-bypass',['--device','/dev/pts/1','--run-loopback','--test-pty']),('console',['--device','/dev/ttyPS0','--run-loopback'])]:
            completed=subprocess.run(['wsl.exe','--exec',posix(out/'uart-host-production'),*args],capture_output=True,timeout=15)
            (out/(name+'.stdout')).write_bytes(completed.stdout);(out/(name+'.stderr')).write_bytes(completed.stderr)
            if completed.returncode!=2:raise ValueError('production refusal gate failed')
            refusals.append(dict(case=name,exit_code=completed.returncode))
        binary=out/'uart-loopback-arm'
        run('ARM-build',['wsl.exe','--exec',posix(TOOL/'arm-linux-gnueabihf-gcc'),'-std=c11','-O2','-Wall','-Wextra','-Werror',
            '-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard','-marm',posix(source),'-o',posix(binary)])
        elf=run('ARM-readelf',['wsl.exe','--exec',posix(TOOL/'arm-linux-gnueabihf-readelf'),'-h','-A','-l','-V',posix(binary)])
        versions=[tuple(map(int,v.split('.'))) for v in re.findall(r'GLIBC_([0-9.]+)',elf)]
        checks=dict(ELF32='ELF32' in elf,ARM='Machine:                           ARM' in elf,
            little_endian='little endian' in elf,hard_float='Tag_ABI_VFP_args: VFP registers' in elf,
            interpreter='/lib/ld-linux-armhf.so.3' in elf,old_board_glibc_2_28=bool(versions) and max(versions)<=(2,28),
            sources_unchanged=all(sha(ROOT/p)==digest for p,digest in hashes.items()))
        if not all(checks.values()):raise ValueError('ARM ABI/input check failed')
        r.update(status='passed_seven_PTY_two_production_refusals_and_ARM_build_not_board_test',
            checks=checks,PTY_cases=7,production_refusals=refusals,binary=str(binary.relative_to(ROOT)),binary_sha256=sha(binary))
        for p in (source,test):shutil_target=out/p.name;shutil_target.write_bytes(p.read_bytes())
    except Exception as e:r.update(status='failed_or_incomplete',error=repr(e))
    save();print(out/'report.json');print(r['status'])
    return 0 if r['status'].startswith('passed_') else 1

if __name__=='__main__':raise SystemExit(main())
