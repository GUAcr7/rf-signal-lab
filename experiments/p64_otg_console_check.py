"""Explicit read-only P201 USB-gadget console diagnostic after JTAG repair.

This is NOT physical JTAG/FTDI recovery or an external UART test. The production
P59 port selection is unchanged. Only the unique Pluto USB console is selected,
then the Linux identity is checked before any board-status reads.
"""
from pathlib import Path
import json,sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from p64_once_uart_boot import control

def main():
    c=None
    with control.operation_lock():
        try:
            c=control.Controller('p64-OTG-console-check');print(c.out,flush=True)
            candidates=[p for p in c.record['ports'] if p['vid']==0x0456 and p['pid']==0xb673
                        and p['description'].startswith('PlutoSDR Serial Console')]
            if len(candidates)!=1:raise ValueError('Unique known Pluto USB console required')
            c.ports={'TX':candidates[0]['device']}
            c.record.update(read_only_board_inspection=True,transport='explicit_USB_gadget_console',
                physical_JTAG_USB_recovered=False,RF_attributes_written=False,buffers_created=False)
            (c.out/'diagnostic.py').write_bytes(Path(__file__).read_bytes())
            with c.board('TX') as (b,identity):
                info=c.inspect('TX',b,identity)
                c.record['TX']=info
                b.command('v=/sys/firmware/devicetree/base/model')
                c.record['model_readback']=b.command('cat $v')
                c.record['uptime']=b.command('cat /proc/uptime')
                c.record['network']=b.command('ifconfig')
                if info['taint']!='0' or info['critical_kernel_fault']:raise ValueError('Kernel health check incomplete')
                required={'ad9361-phy','cf-ad9361-lpc','cf-ad9361-dds-core-lpc'}
                if not required.issubset(info['IIO_names']):raise ValueError('Expected IIO devices missing')
                c.record['boot_stable']=b.value('/proc/sys/kernel/random/boot_id')==info['boot_id']
                if not c.record['boot_stable']:raise ValueError('Boot changed during inspection')
            c.record['status']='passed_P64_P201_Linux_AD9361_readback_over_OTG_not_JTAG_or_RF_test'
        except Exception as error:
            if c:c.record.update(status='failed_or_incomplete_P64_OTG_console_check',error=repr(error))
            else:raise
        finally:
            if c:c.record['serial_closed']=True;c.save();print(c.record['status'],flush=True)
    return 0 if c.record['status'].startswith('passed_') else 1

if __name__=='__main__':raise SystemExit(main())
