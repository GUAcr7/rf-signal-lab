"""Rearm the unchanged accepted profile after this same-boot stability review."""
import argparse,subprocess,sys
from pathlib import Path
from p45_checkpoint import ROOT,read,sha
from p51_save_progress import stable_trial
from p43_finish_enable import checked_units

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('trial','review','units','baseline-enable'):p.add_argument('--'+key,type=Path,required=True)
    args=p.parse_args();trial=read(args.trial);review=read(args.review);base=read(args.baseline_enable)
    stable_trial(trial);checked_units(args.trial,args.review,args.units)
    if (review['status']!='passed_P42_archives_and_independent_NumPy' or review['trial_sha256']!=sha(args.trial)
        or base['status']!='passed_persistent_profile_rearmed_after_two_archived_warm_boots'
        or base.get('display_revision')!='p48' or not base['true_power_cycle_verified']
        or base['expected_boot']!=trial['expected_boot']):raise ValueError('same-boot accepted baseline and stability review required')
    names=('cycle_one','review_one','cycle_two','review_two','units_one','units_two',
        'current_cycle','current_review','current_clock','current_units')
    if set(base['inputs'])!=set(names):raise ValueError('explicit verified baseline references required')
    command=[sys.executable,str(ROOT/'experiments/p43_finish_enable.py')]
    for name in names:
        item=base['inputs'][name];source=Path(item['path']);source=source if source.is_absolute() else ROOT/source
        if sha(source)!=item['sha256']:raise ValueError('baseline reference changed')
        command.extend(('--'+name.replace('_','-'),str(source)))
    return subprocess.run(command,cwd=ROOT,timeout=120).returncode

if __name__=='__main__':raise SystemExit(main())
