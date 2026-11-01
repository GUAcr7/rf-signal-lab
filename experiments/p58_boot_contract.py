"""Permit the new cold proof without relabelling it as a warm boot."""
import re
from pathlib import Path
from p45_checkpoint import ROOT,read,sha

def validate_boot(path):
    b=read(path)
    if not b.get('monitor_started_by_board_init'):raise ValueError('board-started RX required')
    if b['status']=='passed_P57_warm_boot_autonomous_RX_waits_for_fresh_calibration':return b
    if b['status']!='passed_P58_user_power_cycle_autonomous_RX_waits_for_fresh_calibration' or b['reboots_issued']!=0 or b['power_cycles_reported_by_user']!=1 or not b['true_power_cycle_verified']:raise ValueError('accepted cold provenance required')
    for k in ('human_event','passive','poweroff'):
        if sha(ROOT/b[k])!=b[k+'_sha256']:raise ValueError('cold input changed '+k)
    h=read(ROOT/b['human_event']);p=read(ROOT/b['passive']);off=read(ROOT/b['poweroff'])
    if not h['new_board_powercycled_by_user'] or h.get('host_reboot_substituted') or p['UART_bytes_sent']!=0 or not p['startup_ready_observed'] or not p['new_kernel_output_observed']:raise ValueError('cold action/kernel/init proof missing')
    directory=(ROOT/b['passive']).parent
    if sha(directory/'console.txt')!=b['console_sha256'] or (directory/'uart.tx.bin').read_bytes()!=b'':raise ValueError('raw passive transcript or zero-byte claim differs')
    ids=re.findall(r'ORIGINAL_BACKUP_VERIFIED boot=([0-9a-f-]{36})',(directory/'console.txt').read_text(encoding='utf-8'))
    if ids!=[b['expected_boot']] or h['old_boot']==b['expected_boot'] or h['old_boot']!=off['expected_boot'] or not off['halt_observed'] or p['poweroff_report_sha256']!=b['poweroff_sha256']:raise ValueError('cold boot/halt identity differs')
    return b
