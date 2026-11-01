"""Re-identify moved USB devices without RF, reboot or firmware changes.

TJC connect is a read-only ASCII query. The other CH340 candidate must
subsequently pass the existing Linux identity and installed-profile checks.
Only a fully successful proof may replace the host's USB location binding.
"""
from pathlib import Path
import importlib.util
import json
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'host'), str(ROOT/'experiments'), str(ROOT/'src')]
import board_control as control
import serial
from p35_once_merged_trial import AuditPort


def main():
    original = ROOT/'experiments/p78_screen_preflight.py'
    source = original.read_text(encoding='utf-8')
    begin = source.index('            rx = [p for p in ch if')
    end = source.index('            c.ports = dict(', begin)
    replacement = '''            if len(tx)!=1 or len(ch)!=2:
                raise ValueError('Require unique P201 and exactly two CH340 candidates')
            matched = []
            c.record['topology_probe_transactions'] = []
            for candidate in ch:
                folder = c.out/('candidate-'+candidate['device']); folder.mkdir()
                raw = serial.Serial(port=None,baudrate=115200,timeout=.05,write_timeout=1)
                raw.dtr=False;raw.rts=False;raw.port=candidate['device'];raw.open()
                audit = AuditPort(raw,folder)
                response=bytearray()
                try:
                    audit.write(b'connect'+b'\\xff'*3)
                    deadline=time.monotonic()+1.5
                    while time.monotonic()<deadline:
                        response.extend(audit.read(max(1,audit.in_waiting)))
                    if b'comok ' not in response and b'\\x88\\xff\\xff\\xff' in response:
                        audit.write(b'connect'+b'\\xff'*3)
                        deadline=time.monotonic()+1.5
                        while time.monotonic()<deadline:
                            response.extend(audit.read(max(1,audit.in_waiting)))
                finally:
                    audit.close()
                entries=[r for r in bytes(response).split(b'\\xff'*3) if r.startswith(b'comok ')]
                wanted=('comok 1,').encode('ascii')
                exact=[]
                for entry in entries:
                    fields=entry.decode('ascii').split(',')
                    if len(fields)==7 and fields[2]==MODEL and fields[5]==SERIAL and fields[6]=='8388608':
                        exact.append(entry)
                c.record['topology_probe_transactions'].append(dict(
                    port=candidate,response_hex=bytes(response).hex(),exact_screen_matches=len(exact)))
                c.save()
                if len(exact)==1: matched.append(candidate)
            if len(matched)!=1:
                raise ValueError('Expected one exact accepted screen identity, no binding changed')
            screen=matched
            rx=[p for p in ch if p not in screen]
            c.record['candidate_binding_basis']=dict(
                method='exact TJC model/serial/flash first; remaining candidate must pass Linux/profile',
                no_RF=True,source_snapshot_sha256=control.sha(c.out/'preflight.py'))
'''
    source = source[:begin] + replacement + source[end:]
    # Keep __file__ tied to this project for ROOT and record the actual executed source.
    source = source.replace('(c.out/\'preflight.py\').write_bytes(Path(__file__).read_bytes())',
                            "(c.out/'preflight.py').write_text(EXECUTED_SOURCE,encoding='utf-8')")
    namespace = {'__file__': str(original), '__name__': 'p85_rebinding',
                 'EXECUTED_SOURCE': source}
    exec(compile(source, str(original), 'exec'), namespace)
    result = namespace['main']()
    if result:
        return result
    reports=sorted((ROOT/'results').glob('p59-p78-screen-preflight-*/report.json'),
                   key=lambda p:p.stat().st_mtime)
    proof=reports[-1]
    data=json.loads(proof.read_text(encoding='utf-8'))
    if data['status']!='passed_P78_readonly_boards_and_teammate_screen_identity':
        raise ValueError('No accepted topology proof')
    config=ROOT/'configs/board-connections.json'
    (proof.parent/'board-connections.before.json').write_bytes(config.read_bytes())
    bound=json.loads(config.read_text(encoding='utf-8'))
    rx_port=data['resolved_ports']['RX']
    bound['RX_USB_location']=next(p['location'] for p in data['ports'] if p['device']==rx_port)
    bound['RX_USB_binding_evidence']={'report':proof.relative_to(ROOT).as_posix(),
                                    'sha256':control.sha(proof)}
    bound['RX_USB_binding_reason']='P85 exact TJC identity plus other CH340 Linux/profile verified after USB topology change; COM numbers remain unpinned.'
    config.write_text(json.dumps(bound,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('HOST_BINDING_UPDATED',rx_port,bound['RX_USB_location'],flush=True)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
