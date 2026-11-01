"""Bounded non-resetting UART observation after the user-reported power cycle."""
from datetime import datetime,timezone
import json
from pathlib import Path
import re
from serial.tools import list_ports
from p32_session import ROOT,BoardConsole
from p35_once_merged_trial import AuditPort


def main():
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p40-cold-observe-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    r=dict(status='observing',stages=[],port='COM8',DTR=False,RTS=False,reset_command_sent=False,
        user_report='新板已断电并重新上电',cold_cycle_instrument_verified=False,
        ports=[dict(device=p.device,description=p.description,hwid=p.hwid) for p in list_ports.comports()])
    (out/'executed.py').write_bytes(Path(__file__).read_bytes())
    def save():(out/'report.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    board=None;save()
    try:
        board=BoardConsole('COM8',r,save);board.port=AuditPort(board.port,out)
        passive=board.read(8);r['passive_output']=passive;save()
        board.port.write(b'\r');reply=board.read(12);r['after_single_enter']=reply
        (out/'console.txt').write_text(passive+reply,encoding='utf-8')
        r['received_bytes']=len((out/'uart.rx.bin').read_bytes())
        r['status']='UART_silent_boot_state_unknown' if not passive+reply else 'UART_output_preserved_boot_state_requires_classification'
    except Exception as exc:r.update(status='failed',error=repr(exc))
    finally:
        if board:board.close()
        r['serial_closed']=True;save()
    print(out);print(r['status']);print(r.get('passive_output','')+r.get('after_single_enter',''))


if __name__=='__main__':main()
