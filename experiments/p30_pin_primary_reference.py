"""Retain the primary driver header used to cross-check VTC test offsets."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import urllib.error
import urllib.request

ROOT=Path(__file__).resolve().parents[1]


def main():
    out=ROOT/'results'/('p30-primary-reference-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    out.mkdir(exist_ok=False)
    report=dict(attempts=[],status='failed')
    for tag in ['xlnx_rel_v2021.1','xilinx-v2021.1','master']:
        url=f'https://raw.githubusercontent.com/Xilinx/embeddedsw/{tag}/XilinxProcessorIPLib/drivers/vtc/src/xvtc_hw.h'
        try:
            with urllib.request.urlopen(url,timeout=30) as response:data=response.read()
            if b'#define XVTC_GVBHOFF_OFFSET' not in data or b'#define XVTC_GVSHOFF_OFFSET' not in data:
                raise ValueError('expected driver header missing')
            (out/'xvtc_hw.h').write_bytes(data)
            report.update(status='retained_not_executed',url=url,tag=tag,sha256=hashlib.sha256(data).hexdigest(),bytes=len(data))
            report['attempts'].append(dict(url=url,status='downloaded'))
            break
        except (urllib.error.URLError,ValueError) as error:
            report['attempts'].append(dict(url=url,error=str(error)))
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(out);print(report['status'],report.get('tag'))


if __name__=='__main__':main()
