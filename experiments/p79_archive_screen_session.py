"""Archive a stopped P79 screen/RF session with full receiver histories."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'host'),str(ROOT/'src'),str(ROOT/'experiments')]
import board_control as control
from p68_evidence import archive
from rfsig.board_session import WORK,require_tx_off,require_rx_control

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--screen-report',type=Path,required=True);args=ap.parse_args()
    screen=json.loads(args.screen_report.read_text('utf-8'))
    if not screen.get('serial_closed'):raise ValueError('Screen service must release its handles first')
    with control.operation_lock():
        c=control.Controller('p79-session-archive');print(c.out,flush=True)
        c.record.update(screen_report=str(args.screen_report.resolve().relative_to(ROOT)),
                        screen_sha256=control.sha(args.screen_report),chunks=[])
        try:
            c.action('stop');c.status()
            require_tx_off(c.record['boards']['TX']);require_rx_control(c.record['boards']['RX'],running=False)
            c.record.update(after_RX=c.record['boards']['RX'],after_TX=c.record['boards']['TX'])
            with c.board('RX') as (b,identity):
                stage='/tmp/p35-p79arc-'+datetime.now(timezone.utc).strftime('%H%M%S')
                b.command('s='+stage);b.command('test ! -e $s');b.command('mkdir $s');b.command('mkdir $s/data')
                b.command('w='+WORK)
                names=('ai.json','ai-history.jsonl','metrics.json','metrics-history.jsonl','summary.json','progress.json','last-display-packed.bin','fb.raw')
                for name in names:b.command('cp $w/data/'+name+' $s/data/'+name)
                archive(c,b,stage,names)
            c.record.update(status='passed_P79_stopped_RX_full_history_archived',RX_stopped=True,TX_stopped=True)
        except Exception as error:c.record.update(status='failed_or_unconfirmed_P79_archive',error=repr(error))
        finally:
            c.record['serial_closed']=True;c.save();print(c.record['status'],flush=True)
    return 0 if c.record['status'].startswith('passed_') else 1

if __name__=='__main__':raise SystemExit(main())
