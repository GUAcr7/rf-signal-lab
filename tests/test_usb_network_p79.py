"""Wrong host key/boot and malformed task bindings must refuse before RF."""
import json
from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).parents[1]/'host'))
import p201_usb_network as net

def test_network_stream_converts_serial_CR_to_shell_LF():
    class Channel:
        def sendall(self,data):self.data=data
    p=object.__new__(net.NetworkPort);p.channel=Channel()
    assert p.write(b'echo test\r')==10
    assert p.channel.data==b'echo test\n'

def test_binding_refuses_changed_evidence(tmp_path,monkeypatch):
    monkeypatch.setattr(net,'ROOT',tmp_path);monkeypatch.setattr(net,'BINDING',tmp_path/'active.json')
    p=tmp_path/'proof.json';p.write_text(json.dumps(dict(status='passed_P79_USB_serial_and_network_same_P201_boot',binding={'boot_id':'boot'})))
    net.BINDING.write_text(json.dumps(dict(report='proof.json',sha256=net.control.sha(p))))
    assert net.load_binding()=={'boot_id':'boot'}
    p.write_text('{}')
    with pytest.raises(ValueError,match='changed'):net.load_binding()

def test_wrong_SSH_key_closed_before_authentication(tmp_path,monkeypatch):
    class Transport:
        closed=False
        def close(self):self.closed=True
    transport=Transport();monkeypatch.setattr(net,'connect',lambda host:transport)
    monkeypatch.setattr(net,'fingerprint',lambda t:'wrong')
    monkeypatch.setattr(net,'authenticate',lambda t:pytest.fail('Authenticated unverified host'))
    with pytest.raises(ValueError,match='key changed'):
        net.NetworkConsole(dict(host='192.168.2.1',host_key_sha256='expected'),{},lambda:None,tmp_path)
    assert transport.closed

def test_network_board_boot_change_closed_without_yield(tmp_path,monkeypatch):
    class Fake:
        closed=False
        def __init__(self,*args):pass
        def shell(self):pass
        def command(self,s):return 'Linux pzp201' if s=='uname -a' else 'PUZHI PZSDR P201'
        def value(self,s):return 'different-boot'
        def close(self):Fake.closed=True
    monkeypatch.setattr(net,'NetworkConsole',Fake)
    monkeypatch.setattr(net,'load_binding',lambda:dict(boot_id='expected-boot'))
    c=object.__new__(net.PanelController);c.out=tmp_path;c.record={};c.save=lambda:None
    with pytest.raises(ValueError,match='rebooted'):
        with c.board('TX'):pytest.fail('Unbound new boot accepted')
    assert Fake.closed
