"""Bounded physical TJC link check. Buttons cannot start RF in this program."""
from pathlib import Path
from datetime import datetime,timezone
import argparse
import importlib.util
import json
import re
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'experiments'),str(ROOT/'host')]
import serial
from serial.tools import list_ports
from rfsig.tjc_protocol import ReturnParser,ProtocolError,END,set_text
from rfsig.source_screen import PanelSelection,BUTTONS
from p35_once_merged_trial import AuditPort
import board_control as control

class Screen:
    """One outstanding query, fresh replies and raw byte audit; no shell input."""
    def __init__(self,port,out,log):
        raw=serial.Serial(port=None,baudrate=115200,timeout=.02,write_timeout=1)
        raw.dtr=False;raw.rts=False;raw.port=port;raw.open()
        out.mkdir();self.port=AuditPort(raw,out);self.parser=ReturnParser()
        self.touches=[];self.log=log;self.closed=False

    def close(self):
        self.port.close();self.closed=True

    def identify(self):
        # Opening a freshly powered adapter can expose startup bytes. Preserve
        # them, but require a new explicit connect response after settling.
        self.port.read(self.port.in_waiting or 1)
        time.sleep(.2)
        response=b''
        for attempt in range(2):
            self.port.write(b'connect'+END)
            deadline=time.monotonic()+1.5;data=bytearray()
            while time.monotonic()<deadline:
                data.extend(self.port.read(self.port.in_waiting or 1))
            self.log('identify',attempt=attempt,rx_hex=data.hex())
            found=re.findall(rb'comok [^\xff]+\xff\xff\xff',data)
            if len(found)==1:
                response=found[0][:-3].decode('ascii');break
        fields=response.split(',')
        if len(fields)!=7 or fields[2]!='TJC4827T143_011C' or fields[5]!='D1273501630AD655' or fields[6]!='8388608':
            raise ValueError('Screen does not match teammate hardware identity')
        self.parser.reset()
        return dict(model=fields[2],serial=fields[5],raw=response)

    def events(self):
        data=self.port.read(self.port.in_waiting or 1)
        events=self.parser.feed(data)
        for event in events:
            if event.kind=='touch':
                self.touches.append((time.monotonic(),event))
            elif event.kind=='status' and event.code!=1:
                raise ProtocolError('Screen error/reset/sleep: '+hex(event.code))
        return events

    def query(self,command,kind,expected=None,timeout=.4):
        # Consume anything already queued before issuing a new transaction.
        # Unsolicited TEXT/NUMBER/PAGE replies are stale/ambiguous, not heartbeats.
        if self.port.in_waiting:
            for event in self.events():
                if event.kind not in ('touch','status'):
                    raise ProtocolError('Unexpected response before a query')
        self.port.write(command.encode('ascii')+END)
        deadline=time.monotonic()+timeout;answers=[]
        while time.monotonic()<deadline:
            events=self.events()
            answers.extend(e for e in events if e.kind not in ('touch','status'))
            if answers:
                if len(answers)!=1 or answers[0].kind!=kind:
                    raise ProtocolError('Ambiguous screen query response')
                result=answers[0].payload
                if expected is not None and result!=expected:
                    raise ProtocolError('Screen readback mismatch')
                return result
        raise TimeoutError('Screen query timeout: '+command)

    def fields(self,values):
        for component,text in values.items():
            self.port.write(set_text(component,text))
            result=self.query('get '+component+'.txt','text',text.encode('ascii'))
            self.log('field_readback',component=component,text=result.decode('ascii'))

    def click(self,button):
        if type(button)!=int or button not in BUTTONS:raise ValueError('Known screen button ID required')
        self.log('scripted_screen_click',button=button)
        self.port.write(('click '+str(button)+',1').encode('ascii')+END)
        time.sleep(.1)
        self.port.write(('click '+str(button)+',0').encode('ascii')+END)

def resolve_screen(proof,ports):
    candidate=proof['screen_candidate']
    found=[p for p in ports if p.vid==0x1a86 and p.pid==0x7523 and p.location==candidate['location']]
    if len(found)!=1:raise ValueError('Screen USB location is missing or ambiguous')
    if found[0].location==control.load_rx_location():raise ValueError('Screen/RX USB locations overlap')
    return found[0].device

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--preflight',type=Path,required=True)
    ap.add_argument('--seconds',type=int,default=300)
    ap.add_argument('--required-buttons',type=int,nargs='+',choices=range(1,10),default=list(range(1,10)))
    ap.add_argument('--scripted-buttons',type=int,nargs='+',choices=range(1,10))
    args=ap.parse_args()
    if not 15<=args.seconds<=600:ap.error('Use 15..600 seconds')
    proof=json.loads(args.preflight.read_text('utf-8'))
    if proof.get('status')!='passed_P78_readonly_boards_and_teammate_screen_identity' or not proof.get('serial_closed'):
        raise ValueError('Completed P78 preflight required')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p78-screen-link-%Y%m%dT%H%M%SZ');out.mkdir()
    r=dict(status='running_P78_physical_screen_no_RF',RF_transmissions=0,board_commands=0,
           direct_board_UART=False,computer_bridge_only=True,serial_closed=False,
           preflight=str(args.preflight.resolve().relative_to(ROOT)),preflight_sha256=control.sha(args.preflight),
           physical_button_ids=[],required_button_ids=sorted(set(args.required_buttons)),events=[],
           input_origin='programmatic_real_screen_click' if args.scripted_buttons else 'human_finger')
    (out/'executed.py').write_bytes(Path(__file__).read_bytes())
    def save():(out/'report.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    def log(kind,**data):
        row=dict(kind=kind,utc=datetime.now(timezone.utc).isoformat(),**data)
        r['events'].append(row);save()
    screen=None;panel=PanelSelection();begin=time.monotonic();last_touch=None
    with control.operation_lock():
        try:
            r['port']=resolve_screen(proof,list_ports.comports());save()
            screen=Screen(r['port'],out/'UART',log);r['identity']=screen.identify()
            screen.query('sendme','page',b'\x00')
            screen.fields(panel.fields('LINK TEST'))
            print(out,flush=True);print('P78 SCREEN READY: NO RF. Touch buttons 1..9.',flush=True)
            heartbeat=time.monotonic()
            planned=list(args.scripted_buttons or []);pending_button=None;next_click=0
            while time.monotonic()-begin<args.seconds:
                if planned and pending_button is None and time.monotonic()>=next_click:
                    pending_button=planned.pop(0);screen.click(pending_button);next_click=time.monotonic()+1
                screen.events()
                while screen.touches:
                    stamp,event=screen.touches.pop(0)
                    effect=panel.touch(event,stamp)
                    if effect is None:continue
                    page,button,edge=event.payload
                    r['physical_button_ids']=sorted(set(r['physical_button_ids']+[button]))
                    if pending_button==button:pending_button=None
                    last_touch=time.monotonic()
                    log('physical_touch',page=page,button=button,name=BUTTONS[button],edge=edge,effect=effect,origin=r['input_origin'])
                    status='LINK TEST'
                    if effect=='check':panel.checked();status='APPLIED'
                    elif effect=='start':status='NO RF TEST'
                    elif effect=='unapplied':status='APPLY'
                    screen.fields(panel.fields(status))
                    r['display_status']=status
                if time.monotonic()-heartbeat>=.5:
                    status=r.get('display_status','LINK TEST')
                    screen.query('get t1.txt','text',status.encode('ascii'))
                    r['heartbeat_count']=r.get('heartbeat_count',0)+1;save();heartbeat=time.monotonic()
                if set(r['required_button_ids'])<=set(r['physical_button_ids']) and last_touch and time.monotonic()-last_touch>5:
                    r['required_buttons_verified']=True;break
            screen.fields(panel.fields('OFFLINE'))
            r.update(status='passed_P78_physical_requested_button_echo_no_RF' if set(r['required_button_ids'])<=set(r['physical_button_ids'])
                     else 'partial_P78_screen_link_waiting_physical_buttons',
                     elapsed_s=time.monotonic()-begin,final_fields=panel.fields('OFFLINE'))
        except Exception as error:
            r.update(status='failed_or_incomplete_P78_physical_screen',error=repr(error))
        finally:
            if screen:screen.close()
            r['serial_closed']=True;save();print(r['status'],flush=True)
    return 0 if r['status'].startswith('passed_') else 1

if __name__=='__main__':raise SystemExit(main())
