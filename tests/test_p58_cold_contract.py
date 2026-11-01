"""Cold startup must not be accepted from a warm reboot or fabricated passive claim."""
import sys,json,hashlib
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'experiments'))
import p58_boot_contract as gate
OLD='00000000-0000-0000-0000-000000000001';NEW='00000000-0000-0000-0000-000000000002'

def setup(tmp_path,monkeypatch):
    monkeypatch.setattr(gate,'ROOT',tmp_path)
    def put(name,v):
        p=tmp_path/name;p.write_text(json.dumps(v),encoding='utf-8');return hashlib.sha256(p.read_bytes()).hexdigest()
    h=dict(new_board_powercycled_by_user=True,host_reboot_substituted=False,old_boot=OLD)
    off=dict(halt_observed=True,expected_boot=OLD);offsha=put('off.json',off)
    p=dict(UART_bytes_sent=0,startup_ready_observed=True,new_kernel_output_observed=True,poweroff_report_sha256=offsha)
    b=dict(status='passed_P58_user_power_cycle_autonomous_RX_waits_for_fresh_calibration',monitor_started_by_board_init=True,
        reboots_issued=0,power_cycles_reported_by_user=1,true_power_cycle_verified=True,expected_boot=NEW)
    for key,name,value in (('human_event','human.json',h),('passive','passive.json',p),('poweroff','off.json',off)):
        b[key]=name;b[key+'_sha256']=put(name,value)
    (tmp_path/'console.txt').write_text('Linux version\np43: ORIGINAL_BACKUP_VERIFIED boot='+NEW+'\n',encoding='utf-8')
    (tmp_path/'uart.tx.bin').write_bytes(b'');b['console_sha256']=gate.sha(tmp_path/'console.txt')
    path=tmp_path/'boot.json';put('boot.json',b);return path,b,h,p,off,put

def test_positive_cold_action_and_raw_uart(tmp_path,monkeypatch):
    path,b,*_=setup(tmp_path,monkeypatch);assert gate.validate_boot(path)['expected_boot']==NEW

@pytest.mark.parametrize('bad',['host_reboot','no_cycle','not_verified','human_denied','uart_written','wrong_boot','old_boot_reused','halt_missing','transcript_changed','passive_sha_changed'])
def test_bad_cold_evidence_rejected(tmp_path,monkeypatch,bad):
    path,b,h,p,off,put=setup(tmp_path,monkeypatch)
    if bad=='host_reboot':b['reboots_issued']=1
    if bad=='no_cycle':b['power_cycles_reported_by_user']=0
    if bad=='not_verified':b['true_power_cycle_verified']=False
    if bad=='human_denied':h['new_board_powercycled_by_user']=False;b['human_event_sha256']=put('human.json',h)
    if bad=='uart_written':(tmp_path/'uart.tx.bin').write_bytes(b'\r')
    if bad=='wrong_boot':b['expected_boot']='00000000-0000-0000-0000-000000000003'
    if bad=='old_boot_reused':b['expected_boot']=OLD
    if bad=='halt_missing':off['halt_observed']=False;b['poweroff_sha256']=put('off.json',off);p['poweroff_report_sha256']=b['poweroff_sha256'];b['passive_sha256']=put('passive.json',p)
    if bad=='transcript_changed':(tmp_path/'console.txt').write_text('changed')
    if bad=='passive_sha_changed':put('passive.json',dict(p,UART_bytes_sent=1))
    put('boot.json',b)
    with pytest.raises(ValueError):gate.validate_boot(path)
