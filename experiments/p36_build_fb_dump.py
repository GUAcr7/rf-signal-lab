"""Offline host geometry checks and ARM cross-build of the read-only FB dumper."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
ARM = Path('E:/FPGA_Tools/ARM-GNU-A-8.3-2019.03/attempt-2/gcc-arm-8.3-2019.03-x86_64-arm-linux-gnueabihf/bin')


def posix(path):
    value = Path(path).resolve().as_posix()
    return '/mnt/' + value[0].lower() + value[2:]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    source = ROOT / 'embedded/p36_fb_dump/p36_fb_dump.c'
    existing_geometry = ROOT / 'results/p35-arm-panel-check-20261020T161014Z/geometry.c'
    out = ROOT / 'results' / datetime.now(timezone.utc).strftime('p36-fb-dump-build-%Y%m%dT%H%M%SZ')
    out.mkdir(exist_ok=False)
    report = dict(schema='rfsig.p36_fb_dump_build.v1', status='running', checks=[], stages=[],
                  board_operations=False, ARM_execution=False,
                  source=str(source), source_sha256=sha(source),
                  geometry_reused_from=str(existing_geometry), geometry_source_sha256=sha(existing_geometry),
                  limitations=['Offline build and synthetic geometry cases; no framebuffer hardware access',
                               'Read-only snapshot does not prove physical scanout or atomic pixels'])

    def save():
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')

    def run(label, command, expected=0):
        result = subprocess.run([str(x) for x in command], capture_output=True, timeout=60)
        (out / (label + '.stdout')).write_bytes(result.stdout)
        (out / (label + '.stderr')).write_bytes(result.stderr)
        report['stages'].append(dict(name=label, command=[str(x) for x in command], exit_code=result.returncode))
        save()
        if result.returncode != expected:
            raise RuntimeError(label + ' unexpected exit ' + str(result.returncode))
        return result.stdout.decode('utf-8', errors='replace')

    def check(name, passed):
        report['checks'].append(dict(name=name, passed=bool(passed)))
        save()
        if not passed:
            raise RuntimeError(name)

    (out / source.name).write_bytes(source.read_bytes())
    (out / Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    save()
    try:
        flags = ['-std=c11', '-O2', '-Wall', '-Wextra', '-Werror']
        host = out / 'p36-fb-dump-host'
        run('host-build', ['wsl.exe', '--exec', '/usr/bin/gcc', *flags, posix(source), '-o', posix(host)])
        # Reuse the P35 geometry cases, omitting its drawing-only memory test.
        geometry = existing_geometry.read_text('utf-8')
        geometry = geometry.replace('#include "arm_panel.c"', '#include "p36_fb_dump.c"')
        first = geometry.index(' uint32_t *memory=')
        last = geometry.index(' f.smem_len=(unsigned int)len-1;')
        geometry = geometry[:first] + geometry[last:]
        geometry = geometry.replace('P35_PANEL_GEOMETRY_PASS', 'P36_FB_GEOMETRY_PASS')
        geometry = geometry.replace(' puts("P36_FB_GEOMETRY_PASS");', ''' assert(valid_output("/tmp/p35-fb-20261021T000000Z/fb.raw"));
 assert(!valid_output("/tmp/p35-/fb.raw"));
 assert(!valid_output("/tmp/p35-a/../fb.raw"));
 assert(!valid_output("/tmp/p35-a/x.raw"));
 assert(!valid_output("/tmp/p35-a;reboot/fb.raw"));
 puts("P36_FB_GEOMETRY_PASS");''')
        (out / 'geometry.c').write_text(geometry, encoding='utf-8', newline='\n')
        run('geometry-build', ['wsl.exe', '--exec', '/usr/bin/gcc', *flags, posix(out / 'geometry.c'), '-o', posix(out / 'geometry')])
        text = run('geometry-test', ['wsl.exe', '--exec', posix(out / 'geometry')])
        check('reused geometry offset stride extent format and output path guards', 'P36_FB_GEOMETRY_PASS' in text)
        for index, arguments in enumerate([[], ['/tmp/p35-a/../fb.raw'], ['/tmp/p35-a/fb.raw;reboot'], ['/tmp/p35-a/x.raw']]):
            run('invalid-arguments-' + str(index), ['wsl.exe', '--exec', posix(host), *arguments], expected=2)
        check('invalid CLI rejected before framebuffer open', True)
        binary = out / 'p36-fb-dump'
        run('arm-build', ['wsl.exe', '--exec', posix(ARM / 'arm-linux-gnueabihf-gcc'), *flags,
                          '-mcpu=cortex-a9', '-mfpu=neon', '-mfloat-abi=hard', '-marm',
                          posix(source), '-o', posix(binary)])
        elf = run('arm-readelf', ['wsl.exe', '--exec', posix(ARM / 'arm-linux-gnueabihf-readelf'),
                                  '-h', '-A', '-l', '-V', '-d', posix(binary)])
        check('ARM32 hardfloat executable', 'ELF32' in elf and 'Machine:                           ARM' in elf
              and 'VFP registers' in elf and '/lib/ld-linux-armhf.so.3' in elf)
        check('source remained pinned', sha(source) == report['source_sha256'])
        report.update(status='passed_offline_geometry_and_ARM_cross_compile_not_board_test',
                      binary=str(binary), binary_sha256=sha(binary), binary_bytes=binary.stat().st_size,
                      host_binary_sha256=sha(host), checks_count=len(report['checks']))
    except Exception as error:
        report.update(status='failed', error=repr(error))
    finally:
        save()
    print(out, flush=True)
    print(report['status'], flush=True)
    return 0 if report['status'].startswith('passed_') else 1


if __name__ == '__main__':
    raise SystemExit(main())
