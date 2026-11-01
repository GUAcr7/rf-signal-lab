"""Read-identify COM9 after owned echo-off P52 transport interruption.

No TX/RX, RF writes, resets or firmware operations. An empty prompt after USB
disruption is not evidence of a dead board. Restore terminal settings only
after verifying the exact existing boot and absence of the bounded source.
"""
import re
from datetime import datetime,timezone
from p45_checkpoint import ROOT,read,write
from p46_console import Console
from p35_once_merged_trial import AuditPort

def main():
    failed=read(ROOT/'results/p52-known-20261024T040217Z/report.json')
    if 'ClearCommError' not in failed['error'] or failed['TX_shell_confirmed']:raise ValueError('specific interrupted owned TX shell required')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p52-tty-recovery-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    r=dict(status='identifying_without_prompt_assumption',stages=[],RF_operations=False,serial_closed=False)
    def save():write(out/'report.json',r)
    board=None;save()
    try:
        board=Console('COM9',r,save);board.port=AuditPort(board.port,out)
        r['passive_output']=board.read(.5);save()
        # These are read-only identity operations, not blind control characters.
        if ('Linux pzp201' not in board.command('uname -a')
            or board.value('/proc/sys/kernel/random/boot_id')!=failed['TX_expected_boot']
            or board.value('/proc/sys/kernel/tainted')!='0'):raise ValueError('old board identity/boot differs')
        ps=board.command('ps')
        if re.search(r'guard --run|arm-tx-source',ps):raise ValueError('source still active; do not modify terminal yet')
        board.command('stty echo');board.command('PS1=$p46_saved_prompt')
        r.update(status='passed_same_boot_read_identity_and_terminal_echo_prompt_restored',expected_boot=failed['TX_expected_boot'])
    except Exception as e:r.update(status='failed_TTY_recovery_no_RF_operations',error=repr(e))
    finally:
        if board:board.close()
        r['serial_closed']=True;save()
    print(out);print(r['status']);return 0 if r['status'].startswith('passed_') else 1
if __name__=='__main__':raise SystemExit(main())
