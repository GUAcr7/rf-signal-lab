"""Verify host archives then halt only the new board for a human power cycle."""
import argparse
from datetime import datetime,timezone
import hashlib,json,re
from pathlib import Path
from p32_session import ROOT,BoardConsole
from p35_once_merged_trial import AuditPort
from p37_review_archives import archive_bytes
from p40_factory_boot import ACTIVE


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--suite-report',type=Path,required=True);args=p.parse_args()
    suite=json.loads(args.suite_report.read_text('utf-8'))
    if suite['status']!='passed_fresh_boot_cancel_restart_120s_RX_LCD_and_archived_NumPy_review' or suite['final_idle_verified'] is not True or suite['serial_closed'] is not True:raise ValueError('completed idle suite required')
    count=0
    for stage in suite['stages']:
        report=Path(stage['report'])
        if hashlib.sha256(report.read_bytes()).hexdigest()!=stage['report_sha256']:raise ValueError('stage changed')
        if stage['label'] in ('short_prefix_archive','cancel_prefix_archive','long_prefix_archive','framebuffer_archive'):
            archive_bytes(report);count+=1
    if count!=4:raise ValueError('all retained prefixes and screen must be archived')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p40-cold-cycle-ready-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    r=dict(status='preflight',stages=[],expected_boot=suite['expected_boot'],suite_report=str(args.suite_report.resolve()),
        host_archives_verified=count,only_new_board=True,old_board_power_action=False,
        shutdown_command_sent=False,cold_power_cycle_performed=False,needs_human_power_cycle=True)
    (out/'executed.py').write_bytes(Path(__file__).read_bytes())
    def save():(out/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    board=None;save()
    try:
        board=BoardConsole('COM8',r,save);board.port=AuditPort(board.port,out);board.shell()
        if 'Zynq-Tronlong' not in board.command('uname -a') or board.value('/proc/sys/kernel/random/boot_id')!=r['expected_boot'] or board.value('/proc/sys/kernel/tainted')!='0':raise ValueError('identity/taint mismatch')
        guard=hashlib.sha256((ROOT/'board/boot/S99board').read_bytes()).hexdigest()
        if guard not in board.command('sha256sum /etc/rcS.d/S99board'):raise ValueError('original guard not restored')
        if re.search(ACTIVE,board.command('ps -ef')):raise ValueError('active experiment; cannot halt')
        board.command('p=/sys/bus/iio/devices');names=board.command('for d in $p/iio:device*;do echo $d;cat $d/name;done')
        matches=re.findall(r'(/sys/bus/iio/devices/iio:device\d+)\r?\ncf-ad9361-lpc\r?$',names,re.M)
        if len(matches)!=1:raise ValueError('ADC ambiguous')
        board.command('cd '+matches[0])
        if board.value('buffer/enable')!='0' or any(board.value('scan_elements/in_voltage'+str(i)+'_en')!='0' for i in range(4)):
            raise ValueError('RX active')
        r['idle_verified']=True;board.command('sync',timeout=20)
        r['status']='normal_poweroff_intent_saved';save()
        board.port.write(b'poweroff\r');r['shutdown_command_sent']=True;save()
        r['shutdown_console']=text=board.read(40,r'System halted')
        (out/'shutdown.txt').write_text(text,encoding='utf-8')
        if 'System halted' not in text:raise ValueError('normal halt not confirmed')
        r['status']='new_board_System_halted_host_archives_verified_waiting_human_cold_cycle'
    except Exception as exc:r.update(status='failed_or_shutdown_unconfirmed',error=repr(exc))
    finally:
        if board:board.close()
        r['serial_closed']=True;save()
    print(out);print(r['status'])
    return 0 if r['status'].startswith('new_board_') else 1


if __name__=='__main__':raise SystemExit(main())
