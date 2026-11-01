"""Rearm the unchanged P48 profile using this recovery's actual warm-boot proof."""
import argparse,subprocess,sys
from pathlib import Path
from p45_checkpoint import ROOT,read,sha

def main():
    p=argparse.ArgumentParser();p.add_argument('--recovery',required=True,type=Path);args=p.parse_args()
    recovery=read(args.recovery)
    if recovery['status']!='passed_ARM_then_current_warm_RF_LCD_clock_IQ_pixels_and_units':raise ValueError('completed current recovery required')
    base=read(ROOT/'results/p43-enabled-20261023T155333Z/report.json')
    command=[sys.executable,str(ROOT/'experiments/p43_finish_enable.py')]
    for name in ('cycle_one','review_one','cycle_two','review_two','units_one','units_two'):
        item=base['inputs'][name];path=Path(item['path'])
        if sha(path)!=item['sha256']:raise ValueError('historical accepted profile proof changed')
        command.extend(['--'+name.replace('_','-'),str(path)])
    for name,key in (('current-warm-cycle','warm_cycle'),('current-warm-review','review'),('current-units','units')):
        command.extend(['--'+name,str(ROOT/recovery[key])])
    return subprocess.run(command,cwd=ROOT,timeout=120).returncode
if __name__=='__main__':raise SystemExit(main())
