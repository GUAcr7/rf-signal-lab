"""Accept existing gated live clock evidence for a user-confirmed power cycle."""
import argparse
from datetime import datetime,timezone
import hashlib,json,re
from pathlib import Path
from p32_session import ROOT
from p36_display_readback import parse_clocks

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text('utf-8'))
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--trial',type=Path,required=True);p.add_argument('--readback',type=Path,required=True);args=p.parse_args()
    t=read(args.trial);r=read(args.readback);boot=t['expected_boot']
    if (t['status']!='passed_long_running_RX_LCD_progress_and_independent_idle' or t.get('startup_origin')!='user_confirmed_power_cycle'
        or t['reboots_issued']!=0 or t['power_cycles_observed']!=1 or not t['independent_final_idle_verified']):raise ValueError('accepted observed power cycle required')
    for item in t['inputs'].values():
        if sha(Path(item['path']))!=item['sha256']:raise ValueError('power cycle evidence changed')
    human=read(Path(t['inputs']['human_event']['path']));capture_path=Path(t['inputs']['passive_capture']['path']);capture=read(capture_path)
    if not human['new_board_powercycled_by_user'] or human['old_boot']==boot or capture['UART_bytes_sent']!=0 or not capture['new_kernel_output_observed'] or not capture['P43_ready_marker_observed']:raise ValueError('power-on evidence missing')
    console=capture_path.parent/'console.txt'
    if not re.search(r'ORIGINAL_BACKUP_VERIFIED boot='+re.escape(boot),console.read_text('utf-8')):raise ValueError('passive boot identity differs')
    if r['status']!='read_only_evidence_collected' or r['expected_boot']!=boot or not r['register_read_gate']['allowed'] or r.get('skip') or r.get('boot_id_after')!=boot or r.get('tainted_after')!='0' or not r.get('serial_closed'):raise ValueError('fresh gated clock read required')
    expected=dict(locked=True,M_integer=16,M_fraction_thousandths=500,D=2,O_integer=25,O_fraction_thousandths=0,
        valid_dividers=True,predicted_33MHz_within_1kHz=True,software_matches_prediction_within_1kHz=True)
    if any(r['decoded'].get(k)!=v for k,v in expected.items()) or r['registers']!={'status':1,'feedback':int('05F41002',16),'output0':25}:raise ValueError('safe-clock decode differs')
    clocks=parse_clocks(r['reads']['clk_summary']['text'])
    for name,target,tolerance in [('fclk0',100000000,1),('fclk1',200000000,2),('43c10000.clk_wiz_mul',1650000000,20),('43c10000.clk_wiz_mul_div',825000000,10),('clk_out1',33000000,1000)]:
        if name not in clocks or abs(clocks[name]['rate_hz']-target)>tolerance:raise ValueError('registered clock differs '+name)
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p43-cold-clock-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    result=dict(status='passed_user_power_cycle_gated_clock_driver_register_consistency',boot_id=boot,trial=str(args.trial.resolve()),trial_sha256=sha(args.trial),
        readback=str(args.readback.resolve()),readback_sha256=sha(args.readback),console_sha256=sha(console),
        decoded=r['decoded'],registers=r['registers'],host_reboots_issued=0,user_reported_power_cycles=1,
        board_operations=False,physical_PCLK_measured=False,PRODUCT_ID_FF_root_cause_closed=False)
    (out/'report.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');(out/'executed.py').write_bytes(Path(__file__).read_bytes());print(out);print(result['status'])
if __name__=='__main__':main()
