"""Regress the observed overflow and independently verify generated DRP resets."""
from datetime import datetime,timezone
import hashlib,json,re
from pathlib import Path
from p32_session import ROOT
from p36_display_readback import parse_clocks

def main():
    prior=ROOT/'results/p36-clockwiz-readback-20261021T031935Z/report.json'
    before=json.loads(prior.read_text('utf-8'))
    clocks=parse_clocks(before['reads']['clk_summary']['text'])
    rate=clocks['fclk0']['rate_hz']
    old=(rate*49500//1000)%(1<<32);old_div=(old+4)//5
    assert old==clocks['43c10000.clk_wiz_mul']['rate_hz']
    assert old_div==clocks['43c10000.clk_wiz_mul_div']['rate_hz']
    new=rate*16500//1000;new_div=(new+1)//2
    assert new<(1<<31) and new_div<(1<<31)
    drp=Path('E:/p37-clock-082321/project/combined.gen/sources_1/bd/system/ip/system_clk_wiz_0_0/system_clk_wiz_0_0_clk_wiz_drp.vhd')
    text=drp.read_text('utf-8')
    assert re.search(r'ram_clk_config\(0\)\s*<=\s*X"05F41002"',text,re.I)
    assert re.search(r'ram_clk_config\(2\)\s*<=\s*X"00000019"',text,re.I)
    report=dict(status='passed_local_observed_overflow_and_generated_DRP_contract',
        board_operations=False,physical_frequency_measured=False,source=str(prior),
        source_sha256=hashlib.sha256(prior.read_bytes()).hexdigest(),
        old_observed_multiplier=old,old_observed_divider=old_div,
        new_predicted_multiplier=new,new_predicted_divider=new_div,
        DRP_source=str(drp),DRP_sha256=hashlib.sha256(drp.read_bytes()).hexdigest(),
        feedback_reset='0x05F41002',output_reset='0x00000019')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p37-clock-contract-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    (out/'executed.py').write_bytes(Path(__file__).read_bytes());print(out);print(report['status'])

if __name__=='__main__':main()
