import json
import numpy as np
import pytest
from test_native_rx_full_p36 import ROOT, posix, run


@pytest.fixture(scope='module')
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp('latest-p39')
    for source, target, flags in [
        (ROOT/'tests/native/mock_latest_panel_p39.c', out/'libiio.so.0', ['-shared', '-fPIC']),
        (ROOT/'embedded/arm_latest_panel_p39/arm_latest_panel_p39.c', out/'monitor', ['-pthread', '-ldl', '-lrt', '-lm']),
    ]:
        result = run(['gcc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                      '-I', posix(ROOT/'embedded/vendor/libiio-v0.24'), posix(source), '-o', posix(target), *flags])
        assert result.returncode == 0, result.stderr.decode(errors='replace')
    return out


def invoke(built, tmp_path, fault='', duration='400', interval='100'):
    output = tmp_path/'output'; log = tmp_path/'release.txt'
    result = run(['env', 'LD_LIBRARY_PATH='+posix(built), 'P36_MOCK_FAULT='+fault,
                  'P36_MOCK_LOG='+posix(log), posix(built/'monitor'), '--analyse-only',
                  posix(output), duration, interval])
    return result, output, log


def test_single_buffer_latest_mailbox_accounting_saved_prefix_and_numerics(built, tmp_path):
    result, out, log = invoke(built, tmp_path)
    assert result.returncode == 0, result.stderr.decode(errors='replace')
    summary = json.loads((out/'summary.json').read_text())
    assert summary['status'] == 'pass' and summary['reason'] == 'duration_complete'
    assert summary['published_prefixes'] > summary['display_updates'] >= 2
    assert summary['consumed_prefixes'] == summary['display_updates']
    assert summary['UI_overwritten_prefixes'] > 0
    assert summary['published_prefixes'] == summary['consumed_prefixes']+summary['UI_overwritten_prefixes']+summary['pending_prefixes_at_stop']
    assert summary['worker_joined'] and summary['RF_after_matches'] and not summary['lossless_proven']
    assert 'destroyed=1 enabled=0 created=1' in log.read_text()
    words = np.fromfile(out/'last-display-packed.bin', dtype='<u2').reshape(8192, 2)
    low = (words & 4095).astype(np.int32)
    expected = ((summary['last_display_sequence']-1)*97+np.arange(8192)) % 4096
    np.testing.assert_array_equal(low[:, 0], expected)
    np.testing.assert_array_equal(low[:, 1], 4095-expected)
    signed = (low ^ 2048)-2048
    x = signed[:, 0]+1j*signed[:, 1]
    window = (.5-.5*np.cos(2*np.pi*np.arange(1024)/1024)).astype(np.float32)
    power = np.mean(abs(np.fft.fft(x.reshape(8, 1024)*window, axis=1))**2, axis=0)/(1024*np.sum(window.astype(float)**2))
    rows = [json.loads(line) for line in result.stdout.decode().splitlines() if line.startswith('{')]
    metrics = [r for r in rows if r['schema']=='rfsig.arm_panel_metrics.v2']
    frames = [r for r in rows if r['schema']=='rfsig.latest_frame.v1']
    assert len(metrics)==len(frames)==summary['display_updates']
    assert frames[-1]['source_block_sequence']==summary['last_display_sequence']
    assert all(a['source_block_sequence'] < b['source_block_sequence'] for a, b in zip(frames, frames[1:]))
    assert abs(metrics[-1]['peak_db']-10*np.log10(max(power))) < .002
    assert abs(metrics[-1]['rms_per_component_counts']-np.sqrt(np.mean(abs(x)**2)/2)) < 1e-6


@pytest.mark.parametrize('fault', ['version', 'config', 'format', 'step', 'end', 'sample_size', 'create', 'short'])
def test_setup_or_refill_error_never_passes_and_releases_resources(built, tmp_path, fault):
    result, out, log = invoke(built, tmp_path, fault=fault)
    assert result.returncode == 1
    summary = json.loads((out/'summary.json').read_text())
    assert summary['status']=='fail' and summary['buffer_released'] and summary['context_released']
    assert not summary['cleanup_unconfirmed'] and not summary['lossless_proven']
    if summary['worker_started']: assert summary['worker_joined']
    if log.exists(): assert 'enabled=0' in log.read_text()


def test_sigterm_during_refill_cancels_and_joins_without_false_duration_pass(built, tmp_path):
    result, out, log = invoke(built, tmp_path, fault='cancel')
    assert result.returncode == 0
    s = json.loads((out/'summary.json').read_text())
    assert s['status']=='stopped' and s['reason']=='signal_requested_stop'
    assert s['worker_joined'] and s['buffer_released'] and not s['cleanup_unconfirmed']
    assert 'destroyed=1 enabled=0 created=1' in log.read_text()


def test_RF_drift_fails_despite_successful_display_updates(built, tmp_path):
    result, out, _ = invoke(built, tmp_path, fault='after_config')
    assert result.returncode == 1
    s = json.loads((out/'summary.json').read_text())
    assert s['status']=='fail' and not s['RF_after_matches']


def test_unjoinable_worker_does_not_destroy_live_buffer(built, tmp_path):
    result, out, log = invoke(built, tmp_path, fault='join_hang', duration='100')
    assert result.returncode == 3 and b'"cleanup_unconfirmed":true' in result.stdout
    assert not (out/'summary.json').exists() and not log.exists()


@pytest.mark.parametrize('duration,interval', [('0','100'), ('120001','100'), ('400x','100'), ('400','0'), ('400','1001')])
def test_invalid_limits_create_no_output(built, tmp_path, duration, interval):
    result, out, _ = invoke(built, tmp_path, duration=duration, interval=interval)
    assert result.returncode == 2 and not out.exists()


def test_existing_output_is_preserved(built, tmp_path):
    out = tmp_path/'output'; out.mkdir(); (out/'sentinel').write_bytes(b'saved')
    result, _, _ = invoke(built, tmp_path)
    assert result.returncode == 2 and (out/'sentinel').read_bytes()==b'saved'
