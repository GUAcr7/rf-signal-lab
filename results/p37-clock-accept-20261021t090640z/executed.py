"""Accept driver/register consistency only; never claim measured external PCLK."""
import argparse
from datetime import datetime,timezone
import hashlib,json
from pathlib import Path
from p32_session import ROOT
from p36_display_readback import parse_clocks
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--trial',required=True,type=Path);p.add_argument('--readback',required=True,type=Path)
    args=p.parse_args();trial=json.loads(args.trial.read_text('utf-8'));read=json.loads(args.readback.read_text('utf-8'))
    if trial['status']!='passed_fresh_boot_merged_probe_and_software_clocks_only':raise RuntimeError('accepted merged trial required')
    for key,wanted in dict(guard_restored=True,fresh_empty_boot_verified=True,reboots_issued=1,PL_programming_attempts=1,overlay_apply_attempts=1,overlay_apply_returned=True,serial_closed=True).items():
        if trial.get(key)!=wanted:raise RuntimeError('trial condition missing '+key)
    bit=Path(trial['bitstream_report']);manifest=json.loads(bit.read_text('utf-8'))
    if sha(bit)!=trial['bitstream_report_sha256'] or manifest.get('safe_clock_32bit_overflow_fix') is not True:raise RuntimeError('safe bit provenance changed')
    if read['status']!='read_only_evidence_collected' or read['expected_boot']!=trial['held_boot'] or not read['register_read_gate']['allowed'] or read.get('skip'):
        raise RuntimeError('fresh same-boot gated register evidence required')
    decoded=read['decoded']
    expected=dict(locked=True,M_integer=16,M_fraction_thousandths=500,D=2,O_integer=25,O_fraction_thousandths=0,
        valid_dividers=True,predicted_33MHz_within_1kHz=True,software_matches_prediction_within_1kHz=True)
    for key,wanted in expected.items():
        if decoded.get(key)!=wanted:raise RuntimeError('clock decode differs '+key)
    if read['registers']!={'status':1,'feedback':int('05F41002',16),'output0':25}:raise RuntimeError('unexpected config/status registers')
    if read.get('boot_id_after')!=trial['held_boot'] or read.get('tainted_after')!='0' or not read.get('serial_closed'):
        raise RuntimeError('boot, kernel or serial release state changed')
    clocks=parse_clocks(read['reads']['clk_summary']['text'])
    for name,target,tolerance in [('fclk0',100000000,1),('fclk1',200000000,2),('43c10000.clk_wiz_mul',1650000000,20),('43c10000.clk_wiz_mul_div',825000000,10),('clk_out1',33000000,1000)]:
        if name not in clocks or abs(clocks[name]['rate_hz']-target)>tolerance:raise RuntimeError('registered rate differs '+name)
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p37-clock-accept-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    report=dict(status='passed_ARM32_clock_overflow_fix_driver_register_consistency_this_boot',
        trial=str(args.trial.resolve()),trial_sha256=sha(args.trial),readback=str(args.readback.resolve()),readback_sha256=sha(args.readback),
        boot_id=trial['held_boot'],registers=read['registers'],decoded=decoded,
        registered_clock_rates={name:clocks[name]['rate_hz'] for name in ['fclk0','fclk1','43c10000.clk_wiz_mul','43c10000.clk_wiz_mul_div','clk_out1']},
        board_operations=False,physical_external_PCLK_measured=False,physical_LCD_visibility_confirmed=False,
        continuous_RF_or_ADC_losslessness_proven=False,CDC_closed=False,production_release=False)
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');(out/'executed.py').write_bytes(Path(__file__).read_bytes())
    print(out);print(report['status'])
if __name__=='__main__':main()
