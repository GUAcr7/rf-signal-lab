import json,re
from pathlib import Path
b=json.loads(Path('E:/p33-ttl-114312/project/combined.srcs/sources_1/bd/system/system.bd').read_text())['design']; t=Path('E:/p33-ttl-114312/hdl/rf_display_top.v').read_text(); s=t[t.index('system i_system_wrapper'):];s=s[:s.index(');')]; bound=set(re.findall(r'\.([a-zA-Z_][a-zA-Z0-9_]*)\s*\(',s));print('bind-only',bound-set(b['ports']));print('BD-only',set(b['ports'])-bound);print('interfaces',b.get('interface_ports',{}).keys())
