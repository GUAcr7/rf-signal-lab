"""Record the paused, stopped archive stage without inheriting a stale running claim."""
import argparse
from pathlib import Path
from p45_checkpoint import ROOT,read,write,sha,rel

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--trial',required=True,type=Path);ap.add_argument('--selection',required=True,type=Path);args=ap.parse_args()
    t=read(args.trial);s=read(args.selection)
    if t['status']!='captured_runtime_AI_pending_byte_archives_and_independent_review' or s['status']!='passed_idle_P57_next_boot_selection_pause' or t['expected_boot']!=s['expected_boot']:raise ValueError('matching stopped paused trial required')
    a=dict(status='P57_stopped_paused_pending_independent_archives',report=rel(args.trial),report_sha256=sha(args.trial),boot=t['boot_report'],
        expected_boot=t['expected_boot'],TX_expected_boot=t['TX_expected_boot'],RX_and_TX_idle=True,serial_closed=True,persistent_AI_selected=False,
        startup_paused_for_archive=True,selection=rel(args.selection),true_power_cycle_verified=False)
    write(ROOT/'results/p57-active.json',a);state=read(ROOT/'TX-SOURCE-STATUS.json');state.update(status=a['status'],authoritative_current_field='p57_current',p57_current=a);write(ROOT/'TX-SOURCE-STATUS.json',state)
    print(a['status'])
if __name__=='__main__':main()
