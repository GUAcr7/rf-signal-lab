"""Build the isolated P48 units display on the unchanged P42 RX engine."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from p36_build_rx_full import ROOT, TOOL, posix


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    out = ROOT/'results'/datetime.now(timezone.utc).strftime('p48-build-%Y%m%dT%H%M%SZ'); out.mkdir(exist_ok=False)
    source = ROOT/'embedded/arm_live_panel_p48/arm_live_panel_p48.c'
    inputs = [source, ROOT/'embedded/arm_panel_p48/arm_panel.c', ROOT/'embedded/arm_panel/font8x12.h',
              ROOT/'embedded/arm_rx_full_p36/arm_rx_full_p36.c', ROOT/'embedded/vendor/libiio-v0.24/iio.h',
              ROOT/'embedded/vendor/libiio-v0.24/source.json', ROOT/'tests/native/mock_latest_panel_p39.c',
              ROOT/'tests/native/mock_rx_full_p36.c', ROOT/'tests/test_native_live_panel_p42.py', ROOT/'tests/test_native_display_p48.py',
              ROOT/'tests/test_native_rx_full_p36.py', Path(__file__)]
    hashes = {p.relative_to(ROOT).as_posix():sha(p) for p in inputs}
    for path in inputs:
        target=out/'inputs'/path.relative_to(ROOT)
        target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(path.read_bytes())
    report = dict(schema='rfsig.p42_build.v1', status='building', inputs_sha256=hashes,
                  stages=[], board_operations=False, lossless_proven=False, runtime_engine='p42', display_revision='p48',
                  replaces_factory_firmware=False,changes_RF_logic=False)
    def save(): (out/'report.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    def execute(label, command, timeout=90):
        r = subprocess.run([str(x) for x in command], capture_output=True, timeout=timeout)
        (out/(label+'.stdout')).write_bytes(r.stdout); (out/(label+'.stderr')).write_bytes(r.stderr)
        report['stages'].append(dict(label=label, command=[str(x) for x in command], exit_code=r.returncode)); save()
        if r.returncode: raise RuntimeError(label+' failed')
        return r.stdout.decode(errors='replace')
    save()
    try:
        execute('tests', [sys.executable, '-m', 'pytest', 'tests/test_native_display_p48.py', '-q', '--junitxml='+str(out/'tests.xml')])
        cases = list(ET.parse(out/'tests.xml').getroot().iter('testcase'))
        if len(cases) < 32 or any(list(c.iter(tag)) for c in cases for tag in ('failure','error','skipped')): raise RuntimeError('test coverage incomplete')
        report['test_count'] = len(cases)
        binary = out/'arm-live-panel-p48'
        execute('cross_compile', ['wsl.exe', '--exec', posix(TOOL/'arm-linux-gnueabihf-gcc'),
            '-std=c11','-O2','-Wall','-Wextra','-Werror','-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard','-marm','-pthread',
            '-I',posix(ROOT/'embedded/vendor/libiio-v0.24'),posix(source),'-o',posix(binary),'-ldl','-lrt','-lm'])
        elf = execute('readelf', ['wsl.exe','--exec',posix(TOOL/'arm-linux-gnueabihf-readelf'),'-h','-A','-l','-V','-d',posix(binary)])
        versions = [tuple(map(int,v.split('.'))) for v in re.findall(r'GLIBC_([0-9.]+)',elf)]
        checks = dict(ELF32='ELF32' in elf, ARM='Machine:                           ARM' in elf,
            little_endian='little endian' in elf,hard_float='Tag_ABI_VFP_args: VFP registers' in elf,
            armhf_interpreter='/lib/ld-linux-armhf.so.3' in elf,glibc_compatible=bool(versions) and max(versions)<=(2,23),
            input_hashes_unchanged=all(sha(ROOT/p)==h for p,h in hashes.items()))
        report['target_checks']=checks
        if not all(checks.values()): raise RuntimeError('ELF/input checks failed')
        report.update(status='passed_native_mock_tests_and_ARM_build_not_board_test',binary=str(binary),binary_sha256=sha(binary),binary_bytes=binary.stat().st_size)
    except Exception as error: report.update(status='failed',error=repr(error))
    save(); print(out); print(report['status'])
    return 0 if report['status'].startswith('passed_') else 1


if __name__=='__main__': raise SystemExit(main())
