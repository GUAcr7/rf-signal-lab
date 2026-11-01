"""Extract and qualify standalone FFT OOC timing/resources; never claim board closure."""
import argparse
import hashlib
import json
from pathlib import Path
import re


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('evidence',type=Path)
    args=parser.parse_args()
    p=args.evidence
    record=json.loads((p/'run-record.json').read_text(encoding='utf-8-sig'))
    assert record['exit_code']==0 and not record['board_accessed'] and not record['bitstream_written']
    text=(p/'routed_timing.rpt').read_text()
    match=re.search(r'WNS\(ns\).*?\n\s*-+.*?\n\s*([\d.-]+)\s+([\d.-]+)\s+(\d+)\s+(\d+)\s+([\d.-]+)\s+([\d.-]+)\s+(\d+)',text)
    assert match and 'All user specified timing constraints are met.' in text
    utilization=(p/'routed_utilization.rpt').read_text()
    resources={}
    for key,label in [('lut','Slice LUTs'),('registers','Slice Registers'),('dsp','DSPs'),('bram36_equivalent','Block RAM Tile')]:
        item=re.search(r'\|\s*'+re.escape(label)+r'\s*\|\s*(\d+)',utilization)
        assert item,label
        resources[key]=int(item[1])
    checks=(p/'check_timing.rpt').read_text()
    assert 'checking unconstrained_internal_endpoints (0)' in checks
    missing_input=int(re.search(r'checking no_input_delay \((\d+)\)',checks)[1])
    missing_output=int(re.search(r'checking no_output_delay \((\d+)\)',checks)[1])
    route=(p/'route_status.rpt').read_text()
    assert re.search(r'nets with routing errors\.*\s*:\s*0',route)
    clock_text=(p/'clocks.rpt').read_text()
    assert 'aclk' in clock_text and '10.000' in clock_text
    checkpoint=Path(record['work'])/'fft1024_routed.dcp'
    assert checkpoint.is_file()
    result={'scope':'standalone out-of-context routed FFT module, no system integration',
      'architecture':record.get('architecture','radix_2_burst_io'),
      'clock_period_ns':10,'setup_wns_ns':float(match[1]),'hold_whs_ns':float(match[5]),
      'failing_setup_endpoints':int(match[3]),'failing_hold_endpoints':int(match[7]),'resources':resources,
      'unconstrained_internal_endpoints':0,'missing_input_delays':missing_input,'missing_output_delays':missing_output,
      'external_clock_buffer_skew_characterized':False,
      'clock_warning':'HD.CLK_SRC not set; clock delay/skew estimation limited',
      'whole_system_timing_passed':False,'board_programmed':False,'bitstream_written':False,
      'checkpoint':str(checkpoint),'checkpoint_sha256':hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
      'reports_sha256':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in p.glob('*.rpt')}}
    (p/'analysis.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
