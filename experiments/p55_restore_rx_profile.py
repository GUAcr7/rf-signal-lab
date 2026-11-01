"""Restore only the previously tested RX manual0/2450MHz after new power-up.

No TX, PL, driver unload or reboot. Live boot/default attributes must match the
fresh read-only preflight before the three established RX writes.
"""
from datetime import datetime,timezone
from p45_checkpoint import ROOT,read,write,sha,rel
from p46_console import Console
from p46_preflight import parse_names
from p36_full_rx_run import RF_EXPECTED
from p35_once_merged_trial import AuditPort

def main():
    pref_path=ROOT/'results/p46-preflight-20261024T074202Z/report.json';pref=read(pref_path)
    if pref['status']!='read_only_both_boards_identified_DMA_idle':raise ValueError('fresh read-only preflight required')
    expected=pref['boards']['COM8'];out=ROOT/'results'/datetime.now(timezone.utc).strftime('p55-rx-profile-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    r=dict(status='preflight',stages=[],preflight=rel(pref_path),preflight_sha256=sha(pref_path),expected_boot=expected['boot_id'],TX_operations=False,PL_changes=False)
    def save():write(out/'report.json',r)
    board=None;save()
    try:
        board=Console('COM8',r,save);board.port=AuditPort(board.port,out);board.shell()
        if board.value('/proc/sys/kernel/random/boot_id')!=expected['boot_id'] or board.value('/proc/sys/kernel/tainted')!='0':raise ValueError('boot/taint changed')
        board.command('ir=/sys/bus/iio/devices');names=parse_names(board.command('for n in $ir/iio:device*;do echo __D__$n:$(cat $n/name)__E__;done'))
        board.command('cd '+names['cf-ad9361-lpc'])
        if board.value('buffer/enable')!='0' or any(board.value('scan_elements/in_voltage'+str(i)+'_en')!='0' for i in range(4)):raise ValueError('RX not idle')
        board.command('cd '+names['ad9361-phy']);r['before']={key:board.value(key) for key in RF_EXPECTED};save()
        if any(r['before'][key]!=expected['RF'][key] for key in RF_EXPECTED):raise ValueError('factory readback changed')
        for name,value in (('in_voltage0_gain_control_mode','manual'),('in_voltage0_hardwaregain','0'),('out_altvoltage0_RX_LO_frequency','2450000000')):
            board.command('a='+name);board.command('echo '+value+' >$a')
        r['after']={key:board.value(key) for key in RF_EXPECTED}
        if r['after']!=RF_EXPECTED:raise ValueError('restored RX attributes differ')
        r['status']='passed_existing_RX_profile_restored_without_TX_or_PL_changes'
    except Exception as e:r.update(status='failed_RX_profile_restore',error=repr(e))
    finally:
        if board:board.close()
        r['serial_closed']=True;save()
    print(out);print(r['status']);return 0 if r['status'].startswith('passed_') else 1
if __name__=='__main__':raise SystemExit(main())
