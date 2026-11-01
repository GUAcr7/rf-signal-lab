import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'experiments'))
from p35_uart_files import upload

class NoDecoder:
    def __init__(self):self.calls=[]
    def command(self,command):
        self.calls.append(command)
        if command=='command -v base64':raise RuntimeError('not found')

def test_missing_decoder_fails_before_files_terminal_or_payload():
    board=NoDecoder()
    with pytest.raises(RuntimeError):upload(board,'/tmp/p35-new/payload',b'data')
    assert board.calls==['command -v base64']
