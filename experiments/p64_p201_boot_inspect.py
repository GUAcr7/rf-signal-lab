"""Read current P201 boot media/clocks under a temporary READ-ONLY mount.

No flash writes, register writes, UART enables, PL loads or reboots.
"""
from datetime import datetime,timezone
import importlib.util,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'experiments')]
spec=importlib.util.spec_from_file_location('p64_control',ROOT/'host/board_control.py')
control=importlib.util.module_from_spec(spec);spec.loader.exec_module(control)

def main():
    c=None
    with control.operation_lock():
        try:
            c=control.Controller('p64-boot-inspect');print(c.out,flush=True)
            c.ports=control.discover_ports(c.record['ports'])
            c.record.update(boot_media_read_only=True,screen_UART_opened=False)
            (c.out/'inspection-script.py').write_bytes(Path(__file__).read_bytes())
            with c.board('TX') as (b,identity):
                before=c.inspect('TX',b,identity);control.require_tx_off(before)
                c.record['before_TX']=before;c.record['resolved_RAM_tmp']=control.board_ram_tmp(b)
                c.record['cmdline']=b.command('cat /proc/cmdline')
                b.command('v=/sys/kernel/debug/clk/clk_summary')
                c.record['clocks']=b.command('if test -f $v;then cat $v;fi')
                b.command('t=/sys/firmware/devicetree/base')
                for name,path in [('UART0_status','$t/amba/serial@e0000000/status'),
                                  ('UART1_status','$t/amba/serial@e0001000/status'),
                                  ('serial0_alias','$t/aliases/serial0'),('serial1_alias','$t/aliases/serial1')]:
                    b.command('v='+path)
                    c.record[name]=b.command('if test -f $v;then od -An -tx1 $v;fi')
                # Refuse to create a second mount of an already mounted card.
                b.command('! grep -q /dev/mmcblk0p1 /proc/mounts')
                directory='/tmp/p35-p64-'+datetime.now(timezone.utc).strftime('%H%M%S')
                b.command('d='+directory);b.command('test ! -e $d');b.command('mkdir $d')
                mounted=False
                try:
                    b.command('mount -t vfat -o ro,nosuid,nodev,noexec /dev/mmcblk0p1 $d')
                    mounted=True
                    mounts=b.command('cat /proc/mounts');c.record['temporary_mounts']=mounts
                    actual=[line.split() for line in mounts.splitlines() if line.startswith('/dev/mmcblk0p1 ')]
                    if len(actual)!=1 or actual[0][1]!=directory or 'ro' not in actual[0][3].split(','):
                        raise ValueError('Read-only mount not proven')
                    c.record['SD_listing']=b.command('ls -la $d')
                    matches={}
                    for name in ('BOOT.bin','devicetree.dtb','uImage','uramdisk.image.gz','uEnv.txt'):
                        digest=c.digest(b,directory+'/'+name);local=Path('D:/FPGA natch/pluto')/name
                        matches[name]=dict(SD_sha256=digest,local_path=str(local),local_sha256=control.sha(local),
                                           identical=digest==control.sha(local))
                    c.record['boot_files']=matches
                    c.record['SD_uEnv']=c.optional(b,directory+'/uEnv.txt')
                finally:
                    if mounted:b.command('umount $d');c.record['temporary_SD_unmounted']=True
                after=c.inspect('TX',b,identity);control.require_tx_off(after)
                if after['boot_id']!=before['boot_id'] or after['RF']!=before['RF']:raise ValueError('Identity/RF changed')
                c.record['after_TX']=after
            c.record['status']='passed_P64_read_only_boot_media_and_clock_inspection'
        except Exception as error:
            if c:c.record.update(status='failed_or_incomplete_P64_boot_inspection',error=repr(error))
            else:raise
        finally:
            if c:c.record['serial_closed']=True;c.save();print(c.record['status'],flush=True)
    return 0 if c.record['status'].startswith('passed_') else 1

if __name__=='__main__':raise SystemExit(main())
