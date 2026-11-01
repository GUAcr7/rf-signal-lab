"""Bounded passive UART capture while the user switches receiver power.

Never sends a UART byte, changes DTR/RTS after open, or claims physical cycling.
"""
import argparse
from datetime import datetime,timezone
import hashlib,json,re,time
from pathlib import Path
from p32_session import ROOT,BoardConsole
from p35_once_merged_trial import AuditPort

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--poweroff-report',type=Path,required=True);args=p.parse_args()
    previous=json.loads(args.poweroff_report.read_text('utf-8'))
    if previous.get('status')!='receiver_halted_checkpoint_verified_awaiting_manual_power_cycle' or previous.get('halt_observed') is not True:raise ValueError('confirmed saved halt required')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p43-passive-power-on-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    r=dict(status='passively_listening',stages=[],poweroff_report=str(args.poweroff_report.resolve()),
        poweroff_report_sha256=hashlib.sha256(args.poweroff_report.read_bytes()).hexdigest(),
        UART_bytes_sent=0,RF_operations=False,PL_operations=False,physical_cycle_verified_by_tool=False,max_seconds=90)
    (out/'executed.py').write_bytes(Path(__file__).read_bytes())
    def save():(out/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    board=None;text='';save()
    try:
        board=BoardConsole('COM8',r,save);board.port=AuditPort(board.port,out)
        begin=time.monotonic()
        while time.monotonic()-begin<90:
            text+=board.read(min(5,90-(time.monotonic()-begin)))
            (out/'console.txt').write_text(text,encoding='utf-8');r['received_characters']=len(text);save()
            if len(text)>2*1024*1024:raise ValueError('passive capture size bound reached')
            if re.search(r'login:\s*$',text) and re.search(r'U-Boot|Booting Linux|Linux version',text):break
        r.update(status='passive_window_completed',new_kernel_output_observed=bool(re.search(r'U-Boot|Booting Linux|Linux version',text)),
            login_observed=bool(re.search(r'login:\s*$',text)),P43_ready_marker_observed='p43: PERSISTENT_MONITOR_READY' in text)
    except Exception as e:r.update(status='capture_incomplete',error=repr(e))
    finally:
        if board:board.close()
        r['serial_closed']=True;r['ended_utc']=datetime.now(timezone.utc).isoformat();save()
    print(out);print(r['status'])
    return 0 if r['status']=='passive_window_completed' else 1
if __name__=='__main__':raise SystemExit(main())
