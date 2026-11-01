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


def test_saved_USB_console_selection_and_explicit_legacy_override(tmp_path, monkeypatch):
    import json
    monkeypatch.setattr(control,'ROOT',tmp_path)
    assert control.load_tx_transport()=='ftdi'
    (tmp_path/'configs').mkdir()
    config=tmp_path/'configs/board-connections.json'
    config.write_text(json.dumps(dict(schema='rfsig.board_connections.v1',TX_transport='usb-console')))
    assert control.load_tx_transport()=='usb-console'
    assert control.load_tx_transport('ftdi')=='ftdi'
    config.write_text(json.dumps(dict(schema='wrong',TX_transport='usb-console')))
    with pytest.raises(ValueError):control.load_tx_transport()
    with pytest.raises(ValueError):control.load_tx_transport('COM10')


def test_wrong_USB_console_Linux_model_is_rejected_and_port_closed(tmp_path,monkeypatch):
    class FakeConsole:
        closed=False
        port=object()
        def __init__(self,*args):pass
        def shell(self):pass
        def command(self,command):
            if command=='uname -a':return 'Linux pzp201 5.10.0'
            if command.startswith('cat /sys/firmware'):return 'Some other board'
            raise AssertionError('Unvalidated board received command: '+command)
        def close(self):FakeConsole.closed=True
    monkeypatch.setattr(control,'Console',FakeConsole)
    monkeypatch.setattr(control,'AuditPort',lambda port,folder:port)
    obj=object.__new__(control.Controller);obj.out=tmp_path;obj.record={}
    obj.tx_transport='usb-console';obj.ports={'TX':'COM10'};obj.save=lambda:None
    with pytest.raises(ValueError,match='expected P201 model'):
        with obj.board('TX'):pytest.fail('Wrong model accepted')
    assert FakeConsole.closed


@pytest.mark.parametrize('arguments', [['send', '--seconds', '61'], ['send', '--seconds', '0'],
                                     ['send', '--signal', 'arbitrary-command'],
                                     ['status', '--tx-transport', 'guess-COM10'],
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
