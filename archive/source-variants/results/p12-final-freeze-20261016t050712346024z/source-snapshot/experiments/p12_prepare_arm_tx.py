"""Build a finite-time ARM TX candidate; only offline checks are executed here."""
import hashlib
import json
import struct
import subprocess
import tarfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = Path('E:/FPGA_Tools/ARM-GNU-A-8.3-2019.03/attempt-2/gcc-arm-8.3-2019.03-x86_64-arm-linux-gnueabihf/bin')


def lp(path):
    value = path.resolve().as_posix()
    return '/mnt/' + value[0].lower() + value[2:]


def main():
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out = ROOT / 'results' / ('p12-arm-tx-prepare-' + stamp)
    out.mkdir()
    prefix = 'arm-tx-source-' + stamp
    bundle = out / prefix
    (bundle / 'bin').mkdir(parents=True)
    source = ROOT / 'embedded/arm_tx_source/arm_tx_source.c'
    header = ROOT / 'embedded/vendor/libiio-v0.24/iio.h'
    provenance = json.loads((header.parent / 'source.json').read_text(encoding='utf-8-sig'))
    assert hashlib.sha256(header.read_bytes()).hexdigest() == provenance['sha256']
    source_bytes = source.read_bytes()
    frozen_source = bundle / source.name
    frozen_source.write_bytes(source_bytes)
    (bundle / header.name).write_bytes(header.read_bytes())
    (bundle / 'source.json').write_bytes((header.parent / 'source.json').read_bytes())

    def command(name, argv, expected=0, reject_text=None):
        run = subprocess.run(argv, capture_output=True, timeout=180)
        (out / (name + '.stdout.txt')).write_bytes(run.stdout)
        (out / (name + '.stderr.txt')).write_bytes(run.stderr)
        if run.returncode != expected:
            raise RuntimeError(f'{name}: unexpected exit {run.returncode}')
        if reject_text is not None:
            assert reject_text.encode() in run.stderr, (name, run.stderr)
            assert all(mark not in run.stdout for mark in (b'libiio=', b'hw_model=', b'CTX_', b'CYCLIC_PUSH'))
        return {'argv': argv, 'exit_code': run.returncode, 'stdout': run.stdout.decode(errors='replace')}

    flags = ['-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-fno-fast-math', '-ffp-contract=off']
    binary = bundle / 'bin/arm-tx-source'
    build = command('arm-compile', ['wsl.exe', '-d', 'Ubuntu-24.04', '--exec', lp(TOOL / 'arm-linux-gnueabihf-gcc'), *flags,
        '-mcpu=cortex-a9', '-mfpu=neon', '-mfloat-abi=hard', '-marm', '-I', lp(bundle), lp(frozen_source), '-o', lp(binary), '-ldl', '-lrt', '-lm', '-pthread'])
    elf = command('arm-elf', ['wsl.exe', '-d', 'Ubuntu-24.04', '--exec', lp(TOOL / 'arm-linux-gnueabihf-readelf'), '-h', '-A', '-l', '-d', '-V', lp(binary)])
    assert 'ELF32' in elf['stdout'] and 'VFP registers' in elf['stdout'] and '/lib/ld-linux-armhf.so.3' in elf['stdout']
    # Full native Linux build. Only SHA/file checks and pre-IIO refusals run here.
    host = out / 'host-check'
    command('host-compile', ['wsl.exe', '-d', 'Ubuntu-24.04', '--exec', 'gcc', *flags,
        '-I', lp(bundle), lp(frozen_source), '-o', lp(host), '-ldl', '-lrt', '-lm', '-pthread'])
    def host_command(name, args, expected=0, reject_text=None):
        return command(name, ['wsl.exe', '-d', 'Ubuntu-24.04', '--exec', lp(host), *args], expected, reject_text)
    fixture = out / 'valid-left-aligned.iq'
    fixture.write_bytes(struct.pack('<8h', -32768, 32752, -16, 0, 16, -32, 1024, -1024))
    sha = hashlib.sha256(fixture.read_bytes()).hexdigest()
    fixture_arg = lp(fixture)
    suffix = ['TEST_SERIAL_NEVER_HARDWARE', 'A', sha, 'RF_LINK_REVIEWED']
    checks = [host_command('sha256-selftest', ['--sha256-selftest'])]
    for name, tail, expected, rejection in [
        ('valid', ['--check', fixture_arg, '4'], 0, None),
        ('valid-sha', ['--check', fixture_arg, '4', sha], 0, None),
        ('wrong-sha', ['--check', fixture_arg, '4', '0' * 64], 2, 'input SHA256 mismatch'),
        ('wrong-count', ['--check', fixture_arg, '5'], 2, 'input rejected'),
        ('negative-count', ['--check', fixture_arg, '-4'], 2, 'usage:'),
        ('missing-token', ['--run', fixture_arg, '4', '30720000', '2450000000', '18000000', '-10', '1', *suffix[:-1]], 2, 'usage:'),
        ('over-duration', ['--run', fixture_arg, '4', '30720000', '2450000000', '18000000', '-10', '61', *suffix], 2, 'usage:'),
        ('nan-duration', ['--run', fixture_arg, '4', '30720000', '2450000000', '18000000', '-10', 'nan', *suffix], 2, 'usage:'),
    ]:
        checks.append(host_command('check-' + name, tail, expected, rejection))
    assert f'INPUT_SHA256={sha}' in checks[1]['stdout']
    bad = out / 'bad-low-bit.iq'
    bad.write_bytes(struct.pack('<8h', 1, 0, 0, 0, 0, 0, 0, 0))
    checks.append(host_command('check-low-bit', ['--check', lp(bad), '4'], 2, 'nonzero discarded low bits'))
    # An explicit run token does not override file rejection; this never reaches dlopen.
    checks.append(host_command('check-run-bad-file', ['--run', lp(bad), '4', '30720000', '2450000000', '18000000', '-10', '1', *suffix], 2, 'nonzero discarded low bits'))
    checks.append(host_command('check-run-wrong-sha', ['--run', fixture_arg, '4', '30720000', '2450000000', '18000000', '-10', '1', *suffix[:2], '0' * 64, suffix[-1]], 2, 'input SHA256 mismatch'))
    if source.read_bytes() != source_bytes:
        raise RuntimeError('Source changed during preparation; preserve this attempt, run again in a new directory')
    (bundle / 'README.txt').write_text(
        'PREPARED CANDIDATE ONLY. No RF transmission or board inspection was executed by preparation.\n'
        'Board libiio must be 0.24, identity PUZHI PZSDR P201. No RF configuration setter exists.\n'
        'Inspect manually if authorized: ./bin/arm-tx-source --inspect\n'
        'Offline file check: ./bin/arm-tx-source --check FILE SAMPLES SHA256\n'
        'The native --run interface additionally requires exact hw_serial, TX port and file SHA256.\n'
        'File: exactly SAMPLES x 2 LE int16 I,Q, effective signed12 codes left-shifted by four.\n'
        'No run.sh and no automatic transmit command are provided. RF run remains pending physical-link review.\n'
        'The software deadline and digital zero are not a hardware RF interlock or proof of RF silence.\n'
        'DDS output is forced to digital zero after buffer release; original DDS enable is deliberately not restored.\n', encoding='ascii', newline='\n')
    sums = [hashlib.sha256(path.read_bytes()).hexdigest() + '  ' + path.relative_to(bundle).as_posix()
            for path in sorted(bundle.rglob('*')) if path.is_file()]
    (bundle / 'SHA256SUMS').write_text('\n'.join(sums) + '\n', encoding='ascii', newline='\n')
    archive = out / (prefix + '.tar')
    with tarfile.open(archive, 'w') as tar:
        for path in sorted(bundle.rglob('*')):
            if path.is_file():
                info = tar.gettarinfo(str(path), arcname=prefix + '/' + path.relative_to(bundle).as_posix())
                info.mode = 0o755 if path.parent.name == 'bin' else 0o644
                with path.open('rb') as stream:
                    tar.addfile(info, stream)
    report = {'status': 'ARM_cross_compile_and_host_file_checks_passed_board_unverified',
              'source_sha256': hashlib.sha256(source_bytes).hexdigest(),
              'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
              'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
              'archive': str(archive), 'prefix': prefix, 'build': build, 'host_checks': checks,
              'board_accessed': False, 'rf_transmitted': False, 'rf_configuration_written': False,
              'host_build': 'WSL native GCC full build; only offline checks and pre-IIO refusals executed by preparation',
              'required_run_bindings': ['P201 hw_model', 'hw_serial', 'TX port', 'exact file SHA256', 'current Fs/TXLO/TXBW/TXGAIN'],
              'deadline': 'local monotonic thread cancels blocked IIO push; SIGALRM only sets stop flag',
              'limitations': ['RF output/LO leakage unmeasured', 'not a hardware interlock', 'board IIO and deadline pending actual controlled-link test']}
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'out': str(out), 'archive': str(archive), 'sha256': report['archive_sha256']}))


if __name__ == '__main__':
    main()
