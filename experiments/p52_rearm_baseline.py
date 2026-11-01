"""Restore the exact P48 next-start selection after P52/P53 bounded experiments.

Uses the current independently archived observed boot, never relabels it as a
human-observed power cycle. Does not start RX, reboot or program PL.
"""
import subprocess,sys
from pathlib import Path
from p45_checkpoint import ROOT,read,sha

def main():
    baseline=read(ROOT/'results/p43-enabled-20261023T155333Z/report.json')
    command=[sys.executable,str(ROOT/'experiments/p43_finish_enable.py')]
    for name in ('cycle_one','review_one','cycle_two','review_two','units_one','units_two'):
        item=baseline['inputs'][name];path=Path(item['path'])
        if sha(path)!=item['sha256']:raise ValueError('prior baseline evidence changed')
        command.extend(['--'+name.replace('_','-'),str(path)])
    for name,path in (
        ('current-observed-cycle','results/p43-observed-cycle-20261024T031944Z/report.json'),
        ('current-observed-review','results/p42-review-20261024T032421Z/report.json'),
        ('current-units','results/p48-unit-review-20261024T034519Z/report.json')):
        command.extend(['--'+name,str(ROOT/path)])
    return subprocess.run(command,cwd=ROOT,timeout=120).returncode
if __name__=='__main__':raise SystemExit(main())
