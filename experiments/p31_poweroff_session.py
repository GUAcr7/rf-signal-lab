"""Normally stop the two idle project boards after the durable stop checkpoint."""
from datetime import datetime, timezone
import json
import re
import time
from p26_retrieve_chunks import ChunkConsole, ROOT


def main():
    state=json.loads((ROOT/'TX-SOURCE-STATUS.json').read_text('utf-8'))
    if not state['session_stop']['user_requested_stop'] or not state['session_stop']['board_sync_complete']:
        raise RuntimeError('saved user stop and board sync required')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('session-poweroff-%Y%m%dT%H%M%SZ')
    out.mkdir(exist_ok=False)
    record=dict(status='stopping',stages=[],boards={},PC_shutdown=False,
        firmware_changes=False,overlay_hot_unload=False)
    def save():
        (out/'report.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    board=None
    save()
    for port,identity,key in [('COM9','Linux pzp201','tx_boot_id'),('COM8','Zynq-Tronlong','rx_boot_id')]:
        item=dict(poweroff_issued=False,halt_observed=False)
        record['boards'][port]=item
        try:
            board=ChunkConsole(port,record,save)
            if identity not in board.command('uname -a'):
                raise RuntimeError('wrong board')
            if state['p31_current'][key] not in board.command('cat /proc/sys/kernel/random/boot_id'):
                raise RuntimeError('boot session changed')
            processes=board.command('ps' if port=='COM9' else 'ps -ef')
            if any(re.search(r'arm-tx-source|p27-rx|arm-rx-capture|iio_readdev',line) for line in processes.splitlines()):
                raise RuntimeError('experiment process still active')
            board.command('command -v poweroff')
            board.command('sync',timeout=20)
            item['intent']='ordinary poweroff after sync'
            save()
            board.port.write(b'poweroff\r')
            item['poweroff_issued']=True
            save()
            raw=bytearray()
            deadline=time.monotonic()+22
            while time.monotonic()<deadline:
                raw.extend(board.port.read(board.port.in_waiting or 1))
                if re.search(rb'(?:reboot: Power down|System halted|system halted|Power down\.)',raw):
                    item['halt_observed']=True
                    break
            item['console']=raw.decode('utf-8',errors='replace')
        except Exception as error:
            item['error']=repr(error)
        finally:
            if board:
                board.close();board=None
            save()
    record['status']='both_boards_normal_powerdown_observed' if all(b['halt_observed'] for b in record['boards'].values()) else 'poweroff_partially_observed_check_console'
    record['serial_handles_closed']=True
    save()
    state['session_stop'].update(poweroff_record=str(out.relative_to(ROOT)/'report.json').replace('\\','/'),
        board_shutdown_issued=all(b['poweroff_issued'] for b in record['boards'].values()),
        both_board_halts_observed=all(b['halt_observed'] for b in record['boards'].values()))
    (ROOT/'TX-SOURCE-STATUS.json').write_text(json.dumps(state,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(out)
    print(record['status'])
    return 0 if state['session_stop']['both_board_halts_observed'] else 1


if __name__=='__main__':raise SystemExit(main())
