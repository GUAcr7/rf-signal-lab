"""Publish a pointer to the actual current task without opening hardware."""
import argparse
from pathlib import Path
from p45_checkpoint import ROOT,read,write,rel

def main():
    p=argparse.ArgumentParser();p.add_argument('--report',required=True,type=Path);args=p.parse_args()
    value=read(args.report)
    current=dict(report=rel(args.report),read_status_from_report=True,
        expected_boot_at_stage_start=value.get('expected_boot',value.get('armed_boot')),
        host_independent_test='results/p52-test-20261024T045844Z/report.json',
        frozen_model='results/p52-export-20261024T043113Z/report.json',
        rule='do not open serial while referenced task is running; all old boot identities are historical',
        record='docs/experiments/EXP-P52-real-RF-AI.md')
    state=read(ROOT/'TX-SOURCE-STATUS.json');state.update(authoritative_current_field='p55_current',p55_current=current)
    write(ROOT/'TX-SOURCE-STATUS.json',state);write(ROOT/'results/p55-active.json',current)
if __name__=='__main__':main()
