import re,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'experiments'))
from p46_console import Console

def test_marker_starts_new_line_even_when_prompt_shares_command_output():
    obj=Console.__new__(Console);obj.name='mock';obj.record={'stages':[]};obj.save=lambda:None
    class Port:
        def write(self,data):self.written=data
    obj.port=Port()
    def read(seconds,pattern):
        marker=re.search(rb'__P46_[a-f0-9]+__',obj.port.written)[0].decode()
        return '# \r\n'+marker+':0\r\n# '
    obj.read=read
    obj.command('stty -echo')
    assert b"printf '\\n__P46_" in obj.port.written
    assert obj.record['stages'][-1]['exit_code']==0
