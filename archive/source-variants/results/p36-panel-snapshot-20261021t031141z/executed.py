"""Draw one frozen, SHA-pinned P27 sparse RX snapshot using the corrected panel.

This does not capture RF, write RF attributes, program PL, apply/remove overlays,
change startup files, or detach the serial console. It uploads a checked small
program into an independent RAM directory, copies the existing frozen RX input,
then compares analysis-only and actual framebuffer-drawing metrics (2 8 1).
Only framebuffer vtconsole bindings may be detached, with original values saved;
they are left detached for later screenshot/readback and are reversible in-boot.
This runner does not infer physical display refresh, live RF, or RF throughput.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import time

from p32_session import BoardConsole, ROOT
from p35_once_merged_trial import AuditPort
from p35_uart_files import upload


BUILD_REPORT = ROOT / 'results/p35-arm-panel-check-20261020T161014Z/report.json'
BINARY_SHA = '39958b75d4d377bcea22a5f153138c58be76291570c80305e883ff658245db77'
SOURCE_SHA = '4a74dcd045caef4fb503946bfbd75f657bc51d0925f4085af6be9b1fc419d911'
FONT_SHA = 'cfd86f35716459278ad17f90a0916f09c085db7b91a6856e49b900aabaefea11'
RF_NAMES = {'ad9361-phy', 'cf-ad9361-lpc', 'cf-ad9361-dds-core-lpc'}
NORMALIZATION = 'mean_fft_power/(N*sum_hann_squared)'
POWER_REFERENCE = '1 count^2 per FFT bin'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def boot_id(value):
    if not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', value):
        raise argparse.ArgumentTypeError('expected a lowercase UUID boot ID')
    return value


def local_evidence(path):
    path = Path(path).resolve(strict=True)
    if not path.is_relative_to((ROOT / 'results').resolve()) or path.name != 'report.json':
        raise ValueError('smoke report must be a report.json in local results')
    return path


def load_inputs(smoke_path):
    """Pure local gate: pin the build and the exact original sparse input contract."""
    smoke_path = local_evidence(smoke_path)
    smoke_bytes = smoke_path.read_bytes()
    smoke = json.loads(smoke_bytes)
    if (smoke.get('status') != 'receiver_abi_layout_capture_and_release_verified'
            or smoke.get('RF_transmitted') is not False):
        raise ValueError('unaccepted receive-only P27 smoke report')
    directory = smoke.get('output_directory', '')
    if not isinstance(directory, str) or not re.fullmatch(r'/tmp/p27-smoke-[0-9]{6}', directory):
        raise ValueError('unexpected P27 board directory')
    meta = smoke.get('native_metadata', {})
    exact = dict(schema='rfsig.sparse_rx_diagnostic.v1', blocks=16,
                 dma_frames=65536, prefix_raw_frames=8192, stride=8,
                 kept_frames_per_block=1024, channels=2,
                 source_format='le:S12/16>>0', storage='LE_s16_IQ_12bit_sign_extended',
                 complete_stream_saved=False, lossless_proven=False,
                 RF_attributes_written=False, kernel_queue_count_modified=False,
                 buffer_released=True)
    for key, expected in exact.items():
        if key not in meta or type(meta[key]) is not type(expected) or meta[key] != expected:
            raise ValueError('unaccepted sparse metadata field: ' + key)
    fs = meta.get('sample_rate_hz')
    if type(fs) is not int or not 1 <= fs <= 100000000:
        raise ValueError('invalid sparse sample rate')
    hashes = []
    original_metadata = []
    for stage in smoke.get('stages', []):
        if stage.get('command') == 'sha256sum prefixes.bin' and stage.get('exit_code') == 0:
            hashes.extend(re.findall(r'^([0-9a-f]{64})\s+prefixes\.bin\r?$', stage.get('output', ''), re.M))
        if stage.get('command') == 'cat metadata.json' and stage.get('exit_code') == 0:
            original_metadata.extend(json.loads(row) for row in stage.get('output', '').splitlines()
                                     if row.startswith('{') and row.endswith('}'))
    if len(hashes) != 1 or original_metadata != [meta]:
        raise ValueError('missing/ambiguous original prefixes SHA or metadata evidence')
    build_bytes = BUILD_REPORT.read_bytes()
    build = json.loads(build_bytes)
    binary_path = BUILD_REPORT.parent / 'arm-panel'
    source_path = ROOT / 'embedded/arm_panel/arm_panel.c'
    font_path = source_path.parent / 'font8x12.h'
    if (build.get('status') != 'passed_host_regressions_and_ARM_cross_compile_not_board_test'
            or not build.get('checks') or not all(c.get('passed') is True for c in build['checks'])
            or Path(build['binary']).resolve() != binary_path.resolve()
            or Path(build['source']).resolve() != source_path.resolve()
            or build.get('binary_sha256') != BINARY_SHA
            or build.get('source_sha256') != SOURCE_SHA or build.get('font_sha256') != FONT_SHA):
        raise ValueError('corrected P35 build contract changed')
    binary = binary_path.read_bytes()
    if (len(binary) != 27172 or build.get('binary_bytes') != len(binary)
            or sha(binary) != BINARY_SHA or sha(source_path.read_bytes()) != SOURCE_SHA
            or sha(font_path.read_bytes()) != FONT_SHA):
        raise ValueError('checked panel binary/source/font bytes changed')
    return dict(smoke=smoke, smoke_bytes=smoke_bytes, smoke_path=smoke_path,
                smoke_sha256=sha(smoke_bytes), source=directory + '/prefixes.bin',
                source_sha256=hashes[0], source_bytes=16 * 1024 * 2 * 2,
                metadata=meta, build=build, build_bytes=build_bytes, binary=binary)


def metrics(output, analyse_only):
    rows = [json.loads(row) for row in output.splitlines() if row.startswith('{')]
    if len(rows) != 1:
        raise RuntimeError('expected exactly one panel metrics JSON row')
    row = rows[0]
    expected = dict(schema='rfsig.arm_panel_metrics.v2', iteration=0, frames=8,
                    power_reference=POWER_REFERENCE, normalization=NORMALIZATION,
                    analyse_only=analyse_only, display_refresh_measured=False,
                    capture_throughput_measured=False)
    for key, value in expected.items():
        if type(row.get(key)) is not type(value) or row[key] != value:
            raise RuntimeError('unexpected metrics field: ' + key)
    for key in ['peak_db', 'rms_per_component_counts', 'spectrum_power_sum_counts_squared',
                'analysis_ms', 'draw_ms', 'iteration_compute_ms']:
        if type(row.get(key)) not in (int, float) or not math.isfinite(row[key]):
            raise RuntimeError('non-finite/nonnumeric metrics: ' + key)
    if (row['rms_per_component_counts'] < 0 or row['spectrum_power_sum_counts_squared'] < 0
            or row['analysis_ms'] < 0 or row['draw_ms'] < 0
            or row['iteration_compute_ms'] + 1e-6 < row['analysis_ms'] + row['draw_ms']):
        raise RuntimeError('invalid metric/timing scope')
    if type(row.get('peak_valid')) is not bool:
        raise RuntimeError('invalid peak validity')
    offset = row.get('peak_offset_bins')
    if row['peak_valid']:
        if type(offset) not in (int, float) or not math.isfinite(offset) or not -512 <= offset <= 511:
            raise RuntimeError('invalid signed peak bin')
    elif offset is not None:
        raise RuntimeError('zero-input peak must be null')
    if (analyse_only and row['draw_ms'] != 0) or (not analyse_only and row['draw_ms'] <= 0):
        raise RuntimeError('draw timing inconsistent with mode')
    return row


def compare_metrics(before, after):
    for key in ['schema', 'iteration', 'frames', 'power_reference', 'normalization',
                'peak_valid', 'peak_offset_bins', 'peak_db', 'rms_per_component_counts',
                'spectrum_power_sum_counts_squared']:
        a, b = before[key], after[key]
        if type(a) in (int, float) and type(b) in (int, float):
            same = math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-7)
        else:
            same = a == b
        if not same:
            raise RuntimeError('analysis/draw numerical disagreement: ' + key)


class PanelConsole(BoardConsole):
    def __init__(self, record, save, out):
        super().__init__('COM8', record, save)
        self.port = AuditPort(self.port, out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-boot', type=boot_id, required=True)
    parser.add_argument('--smoke-report', type=Path, required=True)
    args = parser.parse_args()
    inputs = load_inputs(args.smoke_report)
    guard = (ROOT / 'board/boot/S99board').read_bytes()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out = ROOT / 'results' / ('p36-panel-snapshot-' + stamp)
    out.mkdir(exist_ok=False)
    record = dict(schema='rfsig.p36_panel_snapshot.v1', status='preflight', stages=[],
                  expected_boot=args.expected_boot, smoke_report=str(inputs['smoke_path']),
                  smoke_report_sha256=inputs['smoke_sha256'],
                  source_board_path=inputs['source'], source_sha256=inputs['source_sha256'],
                  source_bytes=inputs['source_bytes'], sparse_metadata=inputs['metadata'],
                  panel_build_report=str(BUILD_REPORT), build_report_sha256=sha(inputs['build_bytes']),
                  binary_sha256=BINARY_SHA, guard_sha256=sha(guard),
                  RF_capture=False, RF_attributes_written=False, PL_programmed=False,
                  overlay_operations=False, startup_files_written=False,
                  UART_console_unbound=False, vtconsole=[], framebuffer_snapshot_read=False,
                  physical_display_verified=False, display_refresh_measured=False,
                  capture_throughput_measured=False, checks=[],
                  limitations=['Frozen sparse RX input, unknown RF target; this is not live RF',
                               'Sparse prefixes have stride 8 and gaps between DMA blocks',
                               'Panel bins/power are digital values; not calibrated RF Hz/dBm',
                               'C analysis/draw timings exclude file I/O, UART and scanout/vsync',
                               'No framebuffer bytes or physical picture are verified by this runner'])

    def save():
        (out / 'report.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')

    def check(name, condition):
        record['checks'].append(dict(name=name, passed=bool(condition)))
        save()
        if not condition:
            raise RuntimeError(name)

    def digest(path):
        if not re.fullmatch(r'/[A-Za-z0-9_./-]+', path) or '..' in path:
            raise ValueError('unsafe board file path')
        board.command('p=' + path)
        found = re.findall(r'^([0-9a-f]{64})\s+\S+\r?$', board.command('sha256sum $p'), re.M)
        if len(found) != 1:
            raise RuntimeError('ambiguous file digest: ' + path)
        return found[0]

    def source_unchanged():
        check('original prefixes SHA', digest(inputs['source']) == inputs['source_sha256'])
        text = board.command('echo __BYTES__$(wc -c < $p)__END__')
        values = re.findall(r'^__BYTES__([0-9]+)__END__\r?$', text, re.M)
        check('original prefixes bytes', values == [str(inputs['source_bytes'])])

    def inspect(label):
        check(label + ' receiver identity', 'Zynq-Tronlong' in board.command('uname -a'))
        check(label + ' same boot', board.value('/proc/sys/kernel/random/boot_id') == args.expected_boot)
        check(label + ' untainted', board.value('/proc/sys/kernel/tainted') == '0')
        check(label + ' RF mode', board.value('/etc/board-mode') == 'rf')
        check(label + ' fabric operating', board.value('/sys/class/fpga_manager/fpga0/state') == 'operating')
        check(label + ' startup guard SHA', digest('/etc/rcS.d/S99board') == sha(guard))
        processes = board.command('ps -ef')
        check(label + ' no competing experiment', not re.search(
            r'arm[-_]panel|arm[-_]rx|p27-rx|p33-cancel|iio_readdev|arm-tx-source|p35-panel-[0-9TZ]+/a', processes))
        board.command('p=/sys/bus/iio/devices')
        text = board.command('for d in $p/iio:device*; do echo $d; cat $d/name; done')
        pairs = re.findall(r'(/sys/bus/iio/devices/iio:device[0-9]+)\r?\n([^\r\n]+)', text)
        names = {name: path for path, name in pairs}
        check(label + ' RF names unique', all(sum(name == n for _, name in pairs) == 1 for n in RF_NAMES))
        check(label + ' RF names present', RF_NAMES <= set(names))
        board.command('cd ' + names['cf-ad9361-lpc'])
        check(label + ' RX buffer idle', board.value('buffer/enable') == '0')
        check(label + ' RX scans idle', all(board.value('scan_elements/in_voltage' + str(i) + '_en') == '0'
                                           for i in range(4)))
        ready = board.command('/etc/rcS.d/S99board --check-rf')
        check(label + ' RF ready', bool(re.search(r'^RF_READY phy=', ready, re.M)))
        board.command('test -e /dev/dri/card0')
        board.command('test -e /dev/fb0')
        geometry = board.value('/sys/class/graphics/fb0/virtual_size')
        found = re.fullmatch(r'([0-9]+),([0-9]+)', geometry)
        check(label + ' virtual framebuffer contains visible panel', bool(found)
              and 800 <= int(found[1]) <= 16384 and 480 <= int(found[2]) <= 16384)
        record.setdefault('framebuffer_observations', []).append(dict(
            phase=label, virtual_size=geometry,
            visible_geometry_validation='corrected arm-panel ioctl before actual draw',
            stride_verified_for_raw_snapshot=False))
        check(label + ' framebuffer 32bpp', board.value('/sys/class/graphics/fb0/bits_per_pixel') == '32')
        source_unchanged()

    board = None
    for name, data in [('executed.py', Path(__file__).read_bytes()),
                       ('smoke-report.json', inputs['smoke_bytes']),
                       ('build-report.json', inputs['build_bytes']),
                       ('arm-panel', inputs['binary']), ('S99board.guard', guard)]:
        (out / name).write_bytes(data)
    save()
    try:
        board = PanelConsole(record, save, out)
        board.shell()
        board.port.write(b'stty echo\r')
        board.read(.4)
        inspect('before')
        directory = '/tmp/p35-panel-' + stamp
        board.command('mkdir ' + directory)
        record['RAM_directory'] = directory
        record['status'] = 'uploading_checked_panel'
        save()
        check('binary upload SHA', upload(board, directory + '/a', inputs['binary']) == BINARY_SHA)
        board.command('d=' + directory)
        board.command('chmod 755 $d/a')
        board.command('s=' + inputs['source'])
        board.command('test ! -e $d/iq')
        board.command('cp $s $d/iq')
        frozen = directory + '/iq'
        check('copied frozen input SHA', digest(frozen) == inputs['source_sha256'])
        source_unchanged()
        record['frozen_input_path'] = frozen
        record['status'] = 'analysis_only_intent'
        save()
        t0 = time.monotonic()
        output = board.command('$d/a --analyse-only $d/iq 2 8 1', timeout=15)
        record['analysis_command_wall_seconds_including_UART'] = time.monotonic() - t0
        record['analysis_metrics'] = first = metrics(output, True)
        save()
        inspect('before draw')
        check('frozen input stable before draw', digest(frozen) == inputs['source_sha256'])
        text = board.command('ls -1d /sys/class/vtconsole/vtcon*')
        consoles = re.findall(r'^(/sys/class/vtconsole/vtcon[0-9]+)\r?$', text, re.M)
        check('vtconsole enumeration unambiguous', bool(consoles) and len(consoles) == len(set(consoles)))
        for path in consoles:
            name, bound = board.value(path + '/name'), board.value(path + '/bind')
            check('vtconsole bind boolean ' + path, bound in ('0', '1'))
            row = dict(path=path, name=name, original_bind=bound, changed=False,
                       restore_command=None)
            record['vtconsole'].append(row)
            save()
            if 'frame buffer' in name.lower() and bound == '1':
                row['change_intent'] = True
                row['restore_command'] = 'echo 1 > ' + path + '/bind'
                save()
                board.command('v=' + path)
                board.command('echo 0 > $v/bind')
                row['changed'] = True
                row['observed_bind_after'] = board.value(path + '/bind')
                check('only framebuffer console detached ' + path, row['observed_bind_after'] == '0')
        record['status'] = 'one_framebuffer_draw_intent'
        record['draw_attempts'] = 1
        save()
        t0 = time.monotonic()
        output = board.command('$d/a $d/iq 2 8 1', timeout=15)
        record['draw_command_wall_seconds_including_UART'] = time.monotonic() - t0
        record['draw_metrics'] = second = metrics(output, False)
        compare_metrics(first, second)
        check('analysis/draw metrics consistent', True)
        check('frozen input stable after draw', digest(frozen) == inputs['source_sha256'])
        inspect('after')
        check('host smoke evidence remained pinned', sha(inputs['smoke_path'].read_bytes()) == inputs['smoke_sha256'])
        record.update(status='passed_frozen_sparse_analysis_and_framebuffer_draw_only',
                      framebuffer_console_bind_left_as_recorded=True,
                      numerical_consistency_verified=True, panel_program_exit_verified=True)
    except Exception as exc:
        record['failure_phase'] = record['status']
        record.update(status='failed_or_state_unconfirmed', error=repr(exc))
        if board:
            try:
                record['passive_failure_tail'] = board.read(3)
            except Exception as tail_error:
                record['passive_tail_error'] = repr(tail_error)
    finally:
        if board:
            try:
                board.close()
            except Exception as close_error:
                record['serial_close_error'] = repr(close_error)
        record['serial_closed'] = board is None or 'serial_close_error' not in record
        record['ended_utc'] = datetime.now(timezone.utc).isoformat()
        save()
    print(out, flush=True)
    print(record['status'], flush=True)
    return 0 if record['status'].startswith('passed_') else 1


if __name__ == '__main__':
    raise SystemExit(main())
