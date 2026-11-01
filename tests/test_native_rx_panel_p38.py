"""Actual composed C receiver/renderer with mock IIO; no serial or board I/O."""
import json
import subprocess
from pathlib import Path

import numpy as np
import pytest

from test_native_rx_full_p36 import posix, run, ROOT


@pytest.fixture(scope='module')
def built(tmp_path_factory):
    directory = tmp_path_factory.mktemp('native-panel-p38')
    include = ROOT / 'embedded/vendor/libiio-v0.24'
    for source, target, flags in [
        (ROOT / 'tests/native/mock_rx_panel_p38.c', directory/'libiio.so.0', ['-shared', '-fPIC']),
        (ROOT / 'embedded/arm_rx_panel_p38/arm_rx_panel_p38.c', directory/'monitor', ['-ldl', '-lrt', '-pthread', '-lm']),
    ]:
        result = run(['gcc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-I', posix(include), posix(source), '-o', posix(target), *flags])
        assert result.returncode == 0, result.stderr.decode(errors='replace')
    return directory


def invoke(built, tmp_path, fault='', cycles='3', interval='100'):
    out = tmp_path/'output'
    result = run(['env', 'LD_LIBRARY_PATH='+posix(built), 'P36_MOCK_FAULT='+fault,
                  posix(built/'monitor'), '--analyse-only', posix(out), cycles, interval])
    return result, out


def test_repeated_new_capture_numerics_and_independent_raw_per_cycle(built, tmp_path):
    result, out = invoke(built, tmp_path)
    assert result.returncode == 0, result.stderr.decode(errors='replace')
    summary = json.loads((out/'summary.json').read_text())
    assert summary['status'] == 'pass' and summary['completed_cycles'] == 3
    assert summary['continuous_RX'] is False and summary['lossless_proven'] is False
    metrics = [json.loads(line) for line in result.stdout.decode().splitlines()
               if line.startswith('{') and 'arm_panel_metrics' in line]
    assert len(metrics) == 3
    for index, row in enumerate(metrics):
        cycle = out/f'cycle-{index:03}'
        meta = json.loads((cycle/'metadata.json').read_text())
        assert meta['worker_joined'] and meta['buffer_released'] and meta['context_released']
        assert meta['completed_blocks'] == 1 and meta['raw_file_complete'] and meta['rf_after_matches']
        words = np.fromfile(cycle/'iq-packed.bin', dtype='<u2')
        assert words.size == 65536*2
        signed = ((words & 4095).astype(np.int32) ^ 2048) - 2048
        iq = signed.reshape(-1, 2)[:8192]
        x = iq[:, 0] + 1j*iq[:, 1]
        window = (.5-.5*np.cos(2*np.pi*np.arange(1024)/1024)).astype(np.float32)
        power = np.mean(abs(np.fft.fft(x.reshape(8, 1024)*window, axis=1))**2, axis=0)/(1024*np.sum(window.astype(float)**2))
        assert row['iteration'] == index and row['analyse_only'] and row['draw_ms'] == 0
        assert abs(row['peak_db']-10*np.log10(np.max(power))) < .002
        assert abs(row['rms_per_component_counts']-np.sqrt(np.mean(abs(x)**2)/2)) < 1e-6


@pytest.mark.parametrize('fault', ['version', 'config', 'format', 'step', 'cancel'])
def test_failed_or_cancelled_capture_stops_before_analysis_or_next_cycle(built, tmp_path, fault):
    result, out = invoke(built, tmp_path, fault=fault)
    assert result.returncode == 1
    summary = json.loads((out/'summary.json').read_text())
    assert summary['status'] == 'fail' and summary['completed_cycles'] == 0
    assert not (out/'cycle-001').exists()
    assert b'arm_panel_metrics' not in result.stdout
    meta = json.loads((out/'cycle-000/metadata.json').read_text())
    assert meta['buffer_released'] and meta['context_released'] and not meta['cleanup_unconfirmed']


@pytest.mark.parametrize('cycles,interval', [('0', '100'), ('65', '100'), ('3x', '100'), ('3', '0'), ('3', '5001')])
def test_invalid_bounds_rejected_before_creating_output(built, tmp_path, cycles, interval):
    result, out = invoke(built, tmp_path, cycles=cycles, interval=interval)
    assert result.returncode == 2 and not out.exists()


def test_existing_directory_never_overwritten(built, tmp_path):
    out = tmp_path/'output'
    out.mkdir()
    (out/'sentinel').write_bytes(b'original')
    result, _ = invoke(built, tmp_path)
    assert result.returncode == 2 and (out/'sentinel').read_bytes() == b'original'
    assert len(list(out.iterdir())) == 1
