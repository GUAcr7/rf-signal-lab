"""Extend the existing guarded warm-boot runner to an identified factory boot.

Historical candidate/profile proofs remain checked. A fresh independent
preflight and explicit restoration of its RX settings bind the actual boot.
No current merged-display verification is inferred before the software reboot.
"""
from p45_checkpoint import ROOT

def main():
    text=(ROOT/'experiments/p43_boot_cycle.py').read_text('utf-8')
    anchor="    p.add_argument('--observe-seconds',type=int,default=20,choices=range(20,901),metavar='20..900')"
    insert="    p.add_argument('--factory-preflight',type=Path,required=True)\n    p.add_argument('--rx-restore',type=Path,required=True)\n"
    if text.count(anchor)!=1:raise ValueError('argument anchor')
    text=text.replace(anchor,insert+anchor)
    anchor='    if args.validate_only:'
    insert='''    factory=read(args.factory_preflight);restored=read(args.rx_restore)
    if (factory['status']!='read_only_both_boards_identified_DMA_idle'
        or restored['status']!='passed_existing_RX_profile_restored_without_TX_or_PL_changes'
        or restored['preflight_sha256']!=sha(args.factory_preflight.read_bytes())
        or restored['expected_boot']!=factory['boards']['COM8']['boot_id']
        or restored['after']!=RF_EXPECTED or not restored['serial_closed']):
        raise ValueError('current factory boot and actual RX restoration required')
    if not args.reuse_cycle:raise ValueError('recover cached proven profile only')
    boot=factory['boards']['COM8']['boot_id'];checked_boot=boot
'''
    if text.count(anchor)!=1:raise ValueError('host gate anchor')
    text=text.replace(anchor,insert+anchor)
    anchor="    (out/'executed.py').write_bytes(Path(__file__).read_bytes())"
    insert='''    r.update(factory_boot_recovery=True,factory_preflight=str(args.factory_preflight.resolve()),
        factory_preflight_sha256=sha(args.factory_preflight.read_bytes()),rx_restore=str(args.rx_restore.resolve()),
        rx_restore_sha256=sha(args.rx_restore.read_bytes()),power_cycles_observed=0,
        startup_origin='controlled_software_reboot_recover_cached_profile_after_powerup',
        historical_candidate_status_report=r.pop('current_status_report',None),
        historical_candidate_status_report_sha256=r.pop('current_status_report_sha256',None))
'''
    if text.count(anchor)!=2:raise ValueError('snapshot anchor count')
    # The validate-only branch writes no hardware report; replace only the
    # second executable snapshot, after the actual recovery record exists.
    first=text.index(anchor);second=text.index(anchor,first+len(anchor))
    text=text[:second]+insert+text[second:]
    text=text.replace("out=ROOT/'results'/('p43-boot-cycle-'+stamp)","out=ROOT/'results'/('p55-recovery-cycle-'+stamp)")
    target=ROOT/'experiments/p55_recovery_cycle.py'
    if target.exists():raise ValueError('preserve generated runner')
    target.write_text(text,encoding='utf-8');print(target)
if __name__=='__main__':main()
