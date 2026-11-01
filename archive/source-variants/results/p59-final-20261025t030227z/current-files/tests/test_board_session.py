"""Failure-oriented checks for the actual board-control boundaries."""
from copy import deepcopy
import pytest
from rfsig.board_session import (WORK, classify_rx, discover_ports, one_json,
                                owned_timeout, require_rx_control, require_tx_off,
                                require_signal_ready, source_directory, score_observations)

BOOT = '48a30fb3-e240-4fee-824d-a46f975d5358'


def running():
    return dict(taint='0', profile_verified=True, init_boot_marker=BOOT, boot_id=BOOT,
                RX_buffer='1', RX_scans=['1'] * 4, exit_code=None,
                progress={'state': 'running'}, AI={'boot_id': BOOT},
                owned_timeout_pid=222, owned_timeout_argv=['timeout', '-k', '22', '930',
                    WORK + '/monitor', WORK + '/data', '900000', '500'],
                progress_advancing=True, RF_matches=True, critical_kernel_fault=False)


def stopped():
    info = running()
    info.update(RX_buffer='0', RX_scans=['0'] * 4, exit_code='0',
                progress={'state': 'stopped'},
                AI={'boot_id': BOOT, 'state': 'STOPPED', 'accepted_class': -1},
                owned_timeout_argv=[], progress_advancing=False)
    return info


def test_USB_number_change_and_unrelated_ports():
    ports = [dict(device='COM27', vid=0x403, pid=0x6010, serial_number='210203859289B'),
             dict(device='COM31', vid=0x1a86, pid=0x7523),
             dict(device='COM10', vid=0x456, pid=0xb673)]
    assert discover_ports(ports) == {'TX': 'COM27', 'RX': 'COM31'}
    with pytest.raises(ValueError):
        discover_ports(ports + [dict(ports[1], device='COM32')])
    with pytest.raises(ValueError):
        discover_ports(ports[1:])


@pytest.mark.parametrize('pid,argv', [(1, None), (True, None), (222, ['sleep', '900']),
    (222, ['timeout', '930', WORK + '/monitor-pretend'])])
def test_reused_or_unowned_PID_is_rejected(pid, argv):
    assert not owned_timeout(pid, argv)


def test_running_and_clean_stop_are_distinct():
    assert classify_rx(running()) == 'RUNNING'
    assert classify_rx(stopped()) == 'STOPPED'
    require_rx_control(running(), running=True)
    require_rx_control(stopped(), running=False)


@pytest.mark.parametrize('change', [
    {'exit_code': '0'}, {'owned_timeout_argv': []},
    {'AI': {'boot_id': 'another-boot'}}, {'RX_buffer': '0'},
    {'profile_verified': False}, {'init_boot_marker': 'stale'}, {'taint': '1'},
])
def test_false_live_evidence_never_passes(change):
    info = running(); info.update(change)
    with pytest.raises(ValueError):
        require_rx_control(info, running=True)


@pytest.mark.parametrize('change', [
    {'RX_scans': ['1', '0', '0', '0']}, {'exit_code': '1'},
    {'AI': {'boot_id': BOOT, 'state': 'STOPPED', 'accepted_class': 1}},
    {'AI': {'boot_id': 'stale', 'state': 'STOPPED', 'accepted_class': -1}},
    {'progress': {'state': 'running'}},
])
def test_incomplete_stop_cannot_be_restarted(change):
    info = stopped(); info.update(change)
    with pytest.raises(ValueError):
        require_rx_control(info, running=False)


def test_nonadvancing_running_must_not_be_treated_as_idle():
    info = running(); info['progress_advancing'] = False
    assert classify_rx(info) == 'RUNNING_PROGRESS_UNCONFIRMED'
    with pytest.raises(ValueError):
        require_rx_control(info, running=False)


def test_calibration_rejects_live_or_nonzero_source():
    off = dict(taint='0', TX_buffer='0', TX_process_observed=False,
               DDS_raw=['0'] * 8, DDS_scale=['0'] * 8)
    require_tx_off(off)
    for key, value in [('TX_buffer', '1'), ('TX_process_observed', True),
                       ('DDS_raw', ['1'] * 8), ('DDS_scale', ['0.1'] * 8)]:
        info = deepcopy(off); info[key] = value
        with pytest.raises(ValueError):
            require_tx_off(info)


def test_wrong_RF_or_kernel_blocks_control():
    for change in ({'RF_matches': False}, {'critical_kernel_fault': True}):
        info = running(); info.update(change)
        with pytest.raises(ValueError):
            require_rx_control(info, running=True)


def test_JSON_frames_not_prompt_or_multiple_results():
    assert one_json('\r\n{"state":"running"}\r\n__P46_123__:0\r\n') == {'state': 'running'}
    assert one_json('__P46_123__:0\r\n', optional=True) is None
    with pytest.raises(ValueError):
        one_json('{"state":1}\n{"state":2}\n')


def test_new_signal_requires_calibration_state_and_token():
    info = running()
    info['AI'].update(state='WAIT_PILOT', ready=False, calibration_token='a' * 32)
    require_signal_ready(info, 'tone')
    with pytest.raises(ValueError):
        require_signal_ready(info, 'qpsk')
    info['AI'].update(state='NO_USABLE_SIGNAL', ready=True)
    require_signal_ready(info, 'qpsk')
    with pytest.raises(ValueError):
        require_signal_ready(info, 'tone')
    info['AI']['calibration_token'] = ''
    with pytest.raises(ValueError):
        require_signal_ready(info, 'qpsk')


def test_cached_RAM_source_is_bound_to_boot_path_and_level():
    source = dict(expected_boot=BOOT, remote_directory='/tmp/p35-p59-20261025T024500Z',
                  source_peak_component_counts=256)
    assert source_directory(source, BOOT) == source['remote_directory']
    for change in ({'expected_boot': 'old'}, {'source_peak_component_counts': 512},
                   {'remote_directory': '/tmp/p35-p59-../../etc'}):
        with pytest.raises(ValueError):
            source_directory(dict(source, **change), BOOT)


def test_stable_score_excludes_switching_but_rejects_uncertain_or_wrong():
    observations = [dict(elapsed_s=100 + n, state='CLASSIFIED', accepted_class=1) for n in range(12)]
    observations[0]['accepted_class'] = 2
    assert score_observations(observations, 1, 12)['passed']
    bad = deepcopy(observations)
    for row in bad[2:10]:
        row.update(state='UNCERTAIN', accepted_class=-1)
    assert not score_observations(bad, 1, 12)['passed']
    wrong = deepcopy(observations)
    for row in wrong[2:10]:
        row['accepted_class'] = 2
    assert not score_observations(wrong, 1, 12)['passed']
    assert not score_observations(observations[:2], 1, 12)['passed']
