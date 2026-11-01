"""No-RF check of explicit BusyBox child launch/termination on USB console."""
from pathlib import Path
import sys,time,re,argparse
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'host'),str(ROOT/'src'),str(ROOT/'experiments')]
import board_control as control

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--usb-network',action='store_true');args=ap.parse_args()
    if args.usb_network:
        from p201_usb_network import PanelController
        cls=PanelController
    else:cls=control.Controller
    c=None
    with control.operation_lock():
        try:
            c=cls('p79-network-child-check' if args.usb_network else 'p79-console-child-check');print(c.out,flush=True);c.status()
            control.require_tx_off(c.record['boards']['TX'])
            with c.board('TX') as (b,identity):
                b.command('test -x /bin/busybox')
                c.record['external_applets']=b.command('/bin/busybox --list | grep -E "^(setsid|timeout)$"')
                c.record['parent_before']=b.command('echo __PARENT__$$')
                b.command('/bin/busybox setsid /bin/busybox sleep 1 </dev/null &')
                time.sleep(1.5)
                c.record['parent_after_detached']=b.command('echo __PARENT__$$')
                b.command('/bin/busybox sleep 8 </dev/null & p79c=$!')
                b.command('/bin/busybox kill -TERM $p79c')
                c.record['wait']=b.command('wait $p79c; echo __WAIT__$?')
                c.record['parent_after_stop']=b.command('echo __PARENT__$$')
                parents=[re.findall(r'^__PARENT__(\d+)\r?$',c.record[k],re.M)
                         for k in ('parent_before','parent_after_detached','parent_after_stop')]
                if not all(len(x)==1 for x in parents) or len({x[0] for x in parents})!=1:
                    raise ValueError('Login shell changed')
                c.record['after_TX']=c.inspect('TX',b,identity);control.require_tx_off(c.record['after_TX'])
            c.record['status']='passed_P79_external_BusyBox_child_launch_stop_no_RF'
            c.record['explicit_USB_network']=args.usb_network
        except Exception as error:
            if c:c.record.update(status='failed_P79_console_child_check',error=repr(error))
            else:raise
        finally:
            if c:c.record['serial_closed']=True;c.save();print(c.record['status'],flush=True)

if __name__=='__main__':main()
