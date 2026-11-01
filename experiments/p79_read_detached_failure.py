"""Read retained detached job results and process state; no new RF operation."""
from pathlib import Path
import sys,json
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'host'),str(ROOT/'src'),str(ROOT/'experiments')]
import board_control as control

def main():
    c=None
    with control.operation_lock():
        try:
            c=control.Controller('p79-detached-failure-read');print(c.out,flush=True);c.status()
            control.require_tx_off(c.record['boards']['TX'])
            old=json.loads((ROOT/'results/p59-p79-panel-run-20261027T124050088131Z/report.json').read_text('utf-8'))
            job=old['job_directory'];c.record['job_directory']=job
            with c.board('TX') as (b,identity):
                for name in ('supervisor.log','native.log','receipt.json','child.pid'):
                    c.record[name]=c.optional(b,job+'/'+name)
                c.record['process_tree']=b.command('ps -o pid,ppid,pgid,sid,comm,args')
            c.record['status']='read_P79_detached_failure_TX_idle'
        except Exception as error:
            if c:c.record.update(status='failed_P79_detached_failure_read',error=repr(error))
            else:raise
        finally:
            if c:c.record['serial_closed']=True;c.save();print(c.record['status'],flush=True)

if __name__=='__main__':main()
