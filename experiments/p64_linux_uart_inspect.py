"""Identify P201's CURRENT Linux UART state, independently of new-board USB.
Only permitted write is DDS raw=0 when idle and all DDS scales are already zero.
"""
from pathlib import Path
import json,sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from p64_once_uart_boot import control
def main():
    c=None
    with control.operation_lock():
        try:
            c=control.Controller('p64-linux-uart-inspect');print(c.out,flush=True)
            # Discovery still requires unique USB candidates; only TX is opened.
            c.ports=control.discover_ports(c.record['ports'])
            with c.board('TX') as (b,identity):
                before=c.inspect('TX',b,identity);c.record['before_TX']=before
                if before['taint']!='0' or before['TX_buffer']!='0' or before['TX_process_observed'] or before['DDS_scale']!=['0']*8:
                    raise ValueError('TX is not idle with zero DDS scales')
                if before['DDS_raw']!=['0']*8:
                    b.command('cd '+before['IIO_names']['cf-ad9361-dds-core-lpc'])
                    b.command('for n in out_altvoltage*_raw;do echo 0 >$n;done')
                    c.record['DDS_raw_zeroed']=True
                c.record['uptime']=b.command('cat /proc/uptime')
                b.command('t=/sys/firmware/devicetree/base')
                for key,path in [('UART0_status','$t/amba/serial@e0000000/status'),
                                 ('serial0_alias','$t/aliases/serial0'),('serial1_alias','$t/aliases/serial1')]:
                    b.command('v='+path);c.record[key]=b.command('if test -f $v;then od -An -tx1 $v;fi')
                c.record['clocks']=b.command('cat /sys/kernel/debug/clk/clk_summary')
                after=c.inspect('TX',b,identity);control.require_tx_off(after);c.record['after_TX']=after
            c.record['status']='passed_P64_current_Linux_UART_inspection_TX_zero_source'
        except Exception as e:
            if c:c.record.update(status='failed_or_incomplete_P64_Linux_inspection',error=repr(e))
            else:raise
        finally:
            if c:c.record['serial_closed']=True;c.save();print(c.record['status'],flush=True)
    return 0 if c.record['status'].startswith('passed_') else 1
if __name__=='__main__':raise SystemExit(main())
