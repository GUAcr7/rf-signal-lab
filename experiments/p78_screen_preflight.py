"""Read-only board identity plus bounded TJC identification; no RF or boot writes."""
from pathlib import Path
from datetime import datetime, timezone
import importlib.util
import json
import shutil
import sys
import time
from zipfile import ZipFile
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'experiments')]
spec = importlib.util.spec_from_file_location('p78_control', ROOT/'host/board_control.py')
control = importlib.util.module_from_spec(spec)
spec.loader.exec_module(control)
import serial
from p35_once_merged_trial import AuditPort

PRIOR = ROOT/'results/p59-p77-cold-20261026T125647601477Z/report.json'
MODEL = 'TJC4827T143_011C'
SERIAL = 'D1273501630AD655'

def main():
    c = None
    with control.operation_lock():
        try:
            c = control.Controller('p78-screen-preflight')
            print(c.out, flush=True)
            (c.out/'preflight.py').write_bytes(Path(__file__).read_bytes())
            ns = {'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
            sources = []
            for name in ('P67-实屏验收记录-20261026.docx', 'P67-联调对接说明-20261026.docx'):
                path = Path.home()/'Downloads'/name
                shutil.copy2(path, c.out/name)
                with ZipFile(path) as z:
                    xml = ET.fromstring(z.read('word/document.xml'))
                text = '\n'.join(''.join(t.text or '' for t in p.findall('.//w:t', ns))
                                 for p in xml.findall('.//w:p', ns))
                (c.out/(path.stem+'.txt')).write_text(text, encoding='utf-8')
                sources.append(dict(original=str(path), sha256=control.sha(path), snapshot=name))
            c.record['teammate_documents'] = sources
            previous = json.loads(PRIOR.read_text('utf-8'))
            old_rx = [p for p in previous['ports'] if p['device'] == previous['resolved_ports']['RX']]
            if len(old_rx) != 1:
                raise ValueError('Prior verified RX USB identity missing')
            ports = c.record['ports']
            tx = [p for p in ports if p['vid']==0x0456 and p['pid']==0xB673
                  and p['description'].startswith('PlutoSDR Serial Console')]
            ch = [p for p in ports if p['vid']==0x1a86 and p['pid']==0x7523]
            rx = [p for p in ch if p['location']==old_rx[0]['location']]
            screen = [p for p in ch if p not in rx]
            if len(tx)!=1 or len(rx)!=1 or len(screen)!=1:
                raise ValueError('Need one prior-topology RX and one extra screen candidate')
            c.record['candidate_binding_basis'] = dict(prior=str(PRIOR.relative_to(ROOT)),
                prior_sha256=control.sha(PRIOR), prior_verified_RX=old_rx[0],
                note='USB topology only selects candidate; actual Linux and screen identities required below')
            c.ports = dict(TX=tx[0]['device'], RX=rx[0]['device'])
            c.record['resolved_ports'] = c.ports
            c.record['screen_candidate'] = screen[0]
            c.save()
            for role in ('TX','RX'):
                with c.board(role) as (b, identity):
                    c.record['boards'][role] = c.inspect(role,b,identity)
            # Only after RX Linux identity is established, query distinct screen candidate.
            folder = c.out/'screen'; folder.mkdir()
            raw = serial.Serial(port=None,baudrate=115200,timeout=.05,write_timeout=1)
            raw.dtr=False;raw.rts=False;raw.port=screen[0]['device'];raw.open()
            port = AuditPort(raw, folder)
            try:
                def request(command, seconds=.8):
                    port.write(command.encode('ascii')+b'\xff'*3)
                    deadline=time.monotonic()+seconds; response=bytearray()
                    while time.monotonic()<deadline:
                        response.extend(port.read(max(1,port.in_waiting)))
                    c.record.setdefault('screen_transactions',[]).append(dict(
                        command=command,response_hex=response.hex(),utc=datetime.now(timezone.utc).isoformat()))
                    c.save()
                    return bytes(response)
                # A newly powered panel may emit its startup frame before accepting
                # the first query. One additional identity query is harmless; do not
                # retry firmware or RF operations here.
                response=request('connect',1.5)
                entries=[r for r in response.split(b'\xff'*3) if r.startswith(b'comok ')]
                if not entries and b'\x88\xff\xff\xff' in response:
                    response=request('connect',1.5)
                    entries=[r for r in response.split(b'\xff'*3) if r.startswith(b'comok ')]
                if len(entries)!=1:
                    raise ValueError('Missing or ambiguous TJC identity response')
                fields=entries[0].decode('ascii').split(',')
                if len(fields)!=7 or fields[2]!=MODEL or fields[5]!=SERIAL or fields[6]!='8388608':
                    raise ValueError('Screen identity differs from teammate acceptance')
                c.record['screen_identity']=dict(model=fields[2],serial=fields[5],flash=int(fields[6]),raw=entries[0].decode('ascii'))
                for name in ('t1','t2','t4'):
                    response=request('get '+name+'.txt')
                    frames=[r[1:] for r in response.split(b'\xff'*3) if r.startswith(b'\x70')]
                    if len(frames)!=1:
                        raise ValueError('Missing or ambiguous text readback: '+name)
                    c.record.setdefault('screen_texts',{})[name]=frames[0].decode('ascii')
                page=request('sendme')
                if b'\x66\x00\xff\xff\xff' not in page:
                    raise ValueError('Expected source page0')
                c.record['screen_page']=0
            finally:
                port.close()
            c.record.update(status='passed_P78_readonly_boards_and_teammate_screen_identity',
                            screen_downloaded_by_this_run=False,
                            screen_writes_scope='connect and read-only get/sendme only',
                            direct_P201_screen_UART_verified=False)
        except Exception as error:
            if c: c.record.update(status='failed_or_incomplete_P78_preflight',error=repr(error))
            else: raise
        finally:
            if c:
                c.record['serial_closed']=True;c.save()
                print(c.record['status'], flush=True)
    return 0 if c.record['status'].startswith('passed_') else 1

if __name__=='__main__': raise SystemExit(main())
