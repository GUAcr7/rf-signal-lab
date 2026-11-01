"""Read back the retained native log after the USB login session ended. No RF."""
from pathlib import Path
import json,re,sys
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'host'),str(ROOT/'src'),str(ROOT/'experiments')]
import source_screen_rf as panel

def main():
    failed=ROOT/'results/p59-p79-panel-run-20261027T122845769091Z/report.json'
    old=json.loads(failed.read_text('utf-8'))
    paths=[x['command'][2:] for x in old['stages'] if x.get('command','').startswith('o=')]
    if len(paths)!=1 or not re.fullmatch(r'/tmp/p35-p59-\d{8}T\d{6}Z/panel-[0-9a-f]{8}\.log',paths[0]):raise ValueError('Log path not unique')
    c=None
    with panel.control.operation_lock():
        try:
            c=panel.control.Controller('p79-stop-recovery');print(c.out,flush=True);c.status()
            c.record['failed_report']=str(failed.relative_to(ROOT));c.record['failed_sha256']=panel.control.sha(failed)
            tx=c.record['boards']['TX'];panel.require_tx_off(tx)
            if tx['boot_id']!=old['boards']['TX']['boot_id']:raise ValueError('TX boot changed')
            with c.board('TX') as (b,identity):
                c.record['native_log']=b.command('cat '+paths[0])
                c.record['native_log_sha256']=c.digest(b,paths[0])
                c.record['inittab']=b.command('cat /etc/inittab')
                c.record['profile']=b.command('cat /etc/profile')
                c.record['shell_options']=b.command('set -o')
                c.record['shell_traps']=b.command('trap')
                c.record['shell_timeout']=b.command('echo TMOUT=${TMOUT-unset}')
                c.record['tty_settings']=b.command('stty -a')
                c.record['dmesg_end']=b.command('dmesg | tail -n 40')
                c.record['TX_after']=c.inspect('TX',b,identity);panel.require_tx_off(c.record['TX_after'])
            c.record['status']='recovered_P79_native_stop_log_same_boot_TX_idle'
        except Exception as error:
            if c:c.record.update(status='failed_P79_stop_recovery',error=repr(error))
            else:raise
        finally:
            if c:c.record['serial_closed']=True;c.save();print(c.record['status'],flush=True)

if __name__=='__main__':main()
