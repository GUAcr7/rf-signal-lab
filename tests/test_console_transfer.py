"""Protocol and refusal checks, no actual serial device."""
import base64,re
import pytest
from rfsig.console_transfer import upload_uudecode

class Port:
    def __init__(self,owner):self.owner=owner;self.writes=[]
    @property
    def in_waiting(self):return 0
    def write(self,data):self.writes.append(data)
class Board:
    def __init__(self,fail=None):self.port=Port(self);self.commands=[];self.fail=fail
    def command(self,command):
        self.commands.append(command)
        if command.startswith('u5r='):self.ready=command[4:]
        if command.startswith('u5d='):self.done=command[4:]
        return ''
    def read(self,seconds,pattern=None):
        if '__UR' in (pattern or ''):return 'missing' if self.fail=='ready' else self.ready+'\r\n'
        if '__UD' in (pattern or ''):return self.done+('1\r\n' if self.fail=='done' else ':0\r\n')
        return ''

def test_binary_data_upload_and_tty_restore(monkeypatch):
    monkeypatch.setattr('rfsig.console_transfer.time.sleep',lambda _:None)
    b=Board();payload=bytes(range(256))*20
    r=upload_uudecode(b,payload,'/tmp/p35-p65-test/pkg.gz')
    sent=b''.join(b.port.writes[2:-1])
    assert base64.b64decode(sent)==payload
    assert b.port.writes[1]==b'begin-base64 600 payload.bin\n'
    assert b.port.writes[-1]==b'====\n'
    assert b.commands[-1]=='stty "$u5tty"'
    assert r['protocol_complete'] and not r['remote_SHA_verified_by_this_function']

@pytest.mark.parametrize('path',['/etc/uEnv.txt','/tmp/p35-test/../boot','/tmp/p35-test/a;reboot',
                               '/tmp/p35-test/a\nb','/tmp/unverified/a'])
def test_destination_rejected_before_board_access(path):
    b=Board()
    with pytest.raises(ValueError):upload_uudecode(b,b'data',path)
    assert not b.commands and not b.port.writes

@pytest.mark.parametrize('failure',['ready','done'])
def test_failed_transfer_interrupts_decoder_and_restores_tty(monkeypatch,failure):
    monkeypatch.setattr('rfsig.console_transfer.time.sleep',lambda _:None)
    b=Board(failure)
    with pytest.raises(RuntimeError):upload_uudecode(b,b'data','/tmp/p35-test/pkg.gz')
    assert b'\x03\r' in b.port.writes and b.commands[-1]=='stty "$u5tty"'
