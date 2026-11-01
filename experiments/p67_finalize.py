"""Save a verified P67 recovery increment without any board operation."""
from datetime import datetime,timezone
from pathlib import Path
import hashlib,json,zipfile
from p45_checkpoint import ROOT,read,write,sha,rel

def main():
    trial=ROOT/'results/p59-p67-dashboard-trial-20261026T021044611428Z/report.json'
    review=ROOT/'results/p67-board-review-20261026T021543Z/report.json'
    offline=ROOT/'results/p67-offline-20261026T020736Z/report.json'
    build=ROOT/'results/p67-build-20261026T020336Z/report.json'
    t,v=read(trial),read(review)
    if (t['status']!='passed_P67_RAM_RX_dashboard_120s_byte_archived_pending_review'
        or v['status']!='passed_P67_board_snapshot_numerics_and_plot_parity_physical_pending'
        or v['trial_sha256']!=sha(trial) or not v['model_SHA_unchanged']
        or not v['frozen_startup_unchanged'] or not t['serial_closed']):raise ValueError('stopped reviewed trial required')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p67-final-%Y%m%dT%H%M%SZ');out.mkdir()
    event=dict(created_utc=datetime.now(timezone.utc).isoformat(),source='direct_user_answer_in_this_chat',
        user_answer='能看到四区，但只看到停止画面',four_quadrants_visible=True,
        physical_motion_observed=False,stop_screen_expected_after_120s=True)
    write(out/'human-observation.json',event)
    status=dict(status='passed_P67_RAM_dashboard_numerics_static_visibility_motion_pending',
        created_utc=datetime.now(timezone.utc).isoformat(),trial=rel(trial),trial_sha256=sha(trial),
        review=rel(review),review_sha256=sha(review),offline=rel(offline),offline_sha256=sha(offline),
        build=rel(build),build_sha256=sha(build),human=rel(out/'human-observation.json'),
        human_sha256=sha(out/'human-observation.json'),
        TX_boot=t['after_TX']['boot_id'],RX_boot=t['after_RX']['boot_id'],TX_stopped=True,RX_stopped=True,
        serial_closed=True,powered_off=False,RF_transmissions=0,persistent_profile_changed=False,
        physical_static_visibility=True,physical_motion_confirmation=False,
        display_updates=v['display_updates'],duration_software_s=v['elapsed_software_s'],
        AI_accuracy_newly_measured=False,target_bandwidth_validated=False,
        parent_checkpoint='results/p65-final-20261025T125828Z/report.json',
        handoff='docs/handoff/RESUME-P67-20261026.md',checkpoint=rel(out/'checkpoint.zip'))
    write(out/'acceptance.json',status)
    write(ROOT/'results/p67-active.json',dict(status=status['status'],report=rel(out/'acceptance.json'),
        report_sha256=sha(out/'acceptance.json'),handoff=status['handoff'],checkpoint=status['checkpoint']))
    inputs=[ROOT/'START-HERE.md',ROOT/'docs/WORKFLOW-NEXT-20261024.md',
        ROOT/'docs/experiments/EXP-P67-RX-dashboard-20261026.md',ROOT/status['handoff'],
        ROOT/'embedded/arm_live_panel_p67/dashboard.h',ROOT/'tests/test_dashboard_p67.py',
        ROOT/'results/p67-active.json',ROOT/'results/p67-dashboard-tests-20261026.xml',
        out/'acceptance.json',out/'human-observation.json']
    inputs.extend(ROOT/'experiments'/name for name in ('p67_build_dashboard.py','p67_review_offline.py','p67_board_trial.py','p67_review_board.py','p67_finalize.py'))
    for p in (trial,review,offline,build,
        ROOT/'results/p59-status-20261026T014251382824Z/report.json',
        ROOT/'results/p59-status-20261026T020008712130Z/report.json',
        ROOT/'results/p59-status-20261026T020134755588Z/report.json',
        ROOT/'results/p59-p67-dashboard-trial-20261026T020927525797Z/report.json',
        ROOT/'results/p59-source-off-20261026T021020804271Z/report.json'):
        inputs.extend(x for x in p.parent.rglob('*') if x.is_file())
    # Freeze the tested native harness too; no dependence on a future Temp cleanup.
    harness=Path('C:/Users/project_user/AppData/Local/Temp/pytest-of-LENOVO/pytest-136/p67-dashboard0/harness')
    if not harness.is_file():raise ValueError('tested C replay harness missing')
    (out/'tested-replay-harness').write_bytes(harness.read_bytes());inputs.append(out/'tested-replay-harness')
    inputs=sorted(set(inputs))
    manifest={rel(p):dict(bytes=p.stat().st_size,sha256=sha(p)) for p in inputs}
    write(out/'manifest.json',dict(schema='rfsig.recovery_increment.v1',parent=status['parent_checkpoint'],files=manifest))
    archive=out/'checkpoint.zip'
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in inputs:z.write(p,rel(p))
        z.write(out/'manifest.json',rel(out/'manifest.json'))
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:raise ValueError('ZIP CRC failed')
        for name,item in manifest.items():
            data=z.read(name)
            if len(data)!=item['bytes'] or hashlib.sha256(data).hexdigest()!=item['sha256']:raise ValueError('ZIP member mismatch '+name)
    write(out/'report.json',dict(status='passed_P67_increment_zip_CRC_and_all_member_SHA',
        acceptance=rel(out/'acceptance.json'),acceptance_sha256=sha(out/'acceptance.json'),
        checkpoint=rel(archive),checkpoint_bytes=archive.stat().st_size,checkpoint_sha256=sha(archive),
        verified_members=len(manifest),manifest=rel(out/'manifest.json'),manifest_sha256=sha(out/'manifest.json'),
        board_operations=False))
    print(out);print(status['status'])
if __name__=='__main__':main()
