"""Entry validation and local ownership must occur before touching hardware."""
import importlib.util
import os
from pathlib import Path
import sys
import pytest

SPEC = importlib.util.spec_from_file_location(
    'p59_control_test', Path(__file__).resolve().parents[1] / 'host/board_control.py')
control = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(control)


@pytest.mark.parametrize('arguments', [['send', '--seconds', '61'], ['send', '--seconds', '0'],
                                     ['send', '--signal', 'arbitrary-command'],
                                     ['send', '--signal', 'qpsk', '--seconds', '5']])
def test_invalid_entry_exits_before_Controller(monkeypatch, arguments):
    def forbidden(*args):
        raise AssertionError('Controller must not be constructed')
    monkeypatch.setattr(control, 'Controller', forbidden)
    monkeypatch.setattr(sys, 'argv', ['board_control.py'] + arguments)
    with pytest.raises(SystemExit) as error:
        control.main()
    assert error.value.code == 2


@pytest.mark.skipif(os.name != 'nt', reason='Windows board workstation locking')
def test_second_local_controller_cannot_enter_and_lock_is_released(tmp_path, monkeypatch):
    monkeypatch.setattr(control, 'ROOT', tmp_path)
    (tmp_path / 'results').mkdir()
    with control.operation_lock():
        with pytest.raises(OSError):
            with control.operation_lock():
                pytest.fail('Second controller entered')
    with control.operation_lock():
        pass


@pytest.mark.parametrize('action,state', [('start', 'RUNNING'), ('stop', 'STOPPED')])
def test_idempotent_actions_still_check_RF_and_kernel(action, state):
    obj = object.__new__(control.Controller)
    obj.status = lambda: None
    rx = dict(session_state=state, profile_verified=True, taint='0', boot_id='b',
              init_boot_marker='b', RF_matches=False, critical_kernel_fault=True)
    obj.record = {'boards': {'TX': {}, 'RX': rx}}
    with pytest.raises(ValueError):
        obj.action(action)
