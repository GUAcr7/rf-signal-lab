"""Archive the cold-start milestone without changing installed profile proof."""
from datetime import datetime,timezone
import hashlib,zipfile
from p45_checkpoint import ROOT,read,write,sha,rel

def main():
    review=ROOT/'results/p71-review-20261026T041148Z/report.json';v=read(review);trial=ROOT/v['trial'];t=read(trial)
    if (v['status']!='passed_P71_cold_history_FFT_pixels_cleanup_review' or sha(trial)!=v['trial_sha256']
        or not t['serial_closed'] or not t['ten_minute_duration_verified']):raise ValueError('complete cold review required')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p71-final-%Y%m%dT%H%M%SZ');out.mkdir()
    acceptance=dict(status='passed_P71_cold_autonomous_measurement_display_10min_AI_issue_open',
        review=rel(review),review_sha256=sha(review),trial=rel(trial),trial_sha256=sha(trial),
        true_power_cycle_verified=True,ten_minute_duration_verified=True,display_updates=t['display_updates'],
        autonomous_duration_s=t['elapsed_software_s'],maximum_update_interval_s=t['maximum_update_interval_s'],
        TX_boot=t['after_TX']['boot_id'],RX_boot=t['expected_boot'],TX_stopped=True,RX_stopped=True,
        RX_halted=False,powered_off=False,serial_closed=True,host_RX_starts=0,RF_transmissions=0,
        physical_screen_lit_after_session=True,human_dynamic_motion_this_cold_cycle=False,
        selected_profile_configuration='configs/receiver-profile.json',
        installed_profile_unchanged=True,AI_16QAM_acceptance_issue_still_open=True,
        next_task='capture actual uncertain raw blocks; do not relax policy or claim root cause',
        handoff='docs/handoff/RESUME-P71-20261026.md',checkpoint=rel(out/'checkpoint.zip'),
        parent='results/p70-final-20261026T033553Z/report.json')
    write(out/'acceptance.json',acceptance)
    pointer=dict(status=acceptance['status'],report=rel(out/'acceptance.json'),report_sha256=sha(out/'acceptance.json'),
        handoff=acceptance['handoff'],checkpoint=acceptance['checkpoint'],RX_stopped=True,RX_halted=False,
        true_power_cycle_verified=True,ten_minute_duration_verified=True,serial_closed=True)
    write(ROOT/'results/p71-active.json',pointer)
    # This is current-state metadata; the installed warm-profile certificate
    # and its selection hash stay immutable and are not rewritten as cold.
    write(ROOT/'results/p70-active.json',dict(pointer,current_via='results/p71-active.json'))
    source=ROOT/'TX-SOURCE-STATUS.json';data=read(source)
    data.update(status=acceptance['status'],authoritative_current_field='p71_current',p71_current=pointer);write(source,data)
    paths=[out/'acceptance.json',ROOT/'START-HERE.md',source,ROOT/'results/p71-active.json',ROOT/'results/p70-active.json',
        ROOT/'configs/receiver-profile.json',ROOT/'docs/experiments/EXP-P71-cold-metrics-20261026.md',ROOT/acceptance['handoff'],
        ROOT/'docs/design/AI-UNCERTAINTY-20261026.md',ROOT/'docs/WORKFLOW-NEXT-20261024.md',ROOT/'experiments/p70_cold_prepare.py',
        ROOT/'tests/test_p71_passive_startup.py',ROOT/'tests/test_p70_archive_marker.py']
    paths.extend((ROOT/'experiments').glob('p71_*.py'))
    for path in (ROOT/'results').glob('p71-*'):
        if path==out:continue
        paths.extend([path] if path.is_file() else [p for p in path.rglob('*') if p.is_file()])
    for folder in (trial.parent,ROOT/'results/p59-p71-cold-20261026T040119819048Z',(ROOT/t['passive']).parent):
        paths.extend(p for p in folder.rglob('*') if p.is_file())
    paths=sorted(set(paths));manifest={rel(p):dict(bytes=p.stat().st_size,sha256=sha(p)) for p in paths}
    write(out/'manifest.json',dict(schema='rfsig.recovery_increment.v1',parent=acceptance['parent'],files=manifest))
    archive=out/'checkpoint.zip'
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in paths:z.write(p,rel(p))
        z.write(out/'manifest.json',rel(out/'manifest.json'))
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:raise ValueError('ZIP CRC failed')
        for name,item in manifest.items():
            raw=z.read(name)
            if len(raw)!=item['bytes'] or hashlib.sha256(raw).hexdigest()!=item['sha256']:raise ValueError('ZIP member SHA mismatch')
    write(out/'report.json',dict(status='passed_P71_recovery_increment_CRC_all_member_SHA',checkpoint=rel(archive),
        checkpoint_bytes=archive.stat().st_size,checkpoint_sha256=sha(archive),verified_members=len(paths),board_operations=False))
    print(out)
if __name__=='__main__':main()
