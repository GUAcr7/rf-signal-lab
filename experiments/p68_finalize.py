"""Freeze P68 reviewed RF/display work and verify the recovery increment."""
from datetime import datetime,timezone
from pathlib import Path
import hashlib,zipfile
from p45_checkpoint import ROOT,read,write,sha,rel

def main():
    trial=ROOT/'results/p59-p68-rf-dashboard-20261026T022621942828Z/report.json'
    review=ROOT/'results/p68-review-20261026T023538Z/report.json'
    human=ROOT/'results/p68-human-motion-20261026.json';link=ROOT/'results/p68-link-20261026.json'
    t,v=read(trial),read(review)
    if (t['status']!='passed_P68_RF_dashboard_300s_archived_pending_independent_review'
        or v['status']!='passed_P68_controlled_RF_AI_dashboard_history_pixels_Python'
        or v['trial_sha256']!=sha(trial) or not v['controlled_ROI_measurement_diagnostic_passed']
        or not read(human)['physical_motion_confirmed'] or not t['serial_closed']
        or not t['TX_stopped'] or not t['RX_stopped']):raise ValueError('reviewed stopped evidence required')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p68-final-%Y%m%dT%H%M%SZ');out.mkdir()
    status=dict(status='passed_P68_controlled_RF_AI_four_quadrant_dynamic_display',
        created_utc=datetime.now(timezone.utc).isoformat(),trial=rel(trial),trial_sha256=sha(trial),
        review=rel(review),review_sha256=sha(review),human=rel(human),human_sha256=sha(human),
        link=rel(link),link_sha256=sha(link),TX_boot=t['after_TX']['boot_id'],RX_boot=t['after_RX']['boot_id'],
        display_updates=v['display_updates'],duration_software_s=v['duration_software_s'],
        stable_accepted_correct=55,stable_total_modulated_observations=57,stable_uncertain=2,
        physical_dynamic_display_confirmed=True,TX_stopped=True,RX_stopped=True,serial_closed=True,
        powered_off=False,RF_transmissions=4,AI_accuracy_newly_measured=False,
        independent_AI_baseline='P52 INT8 52/54, unchanged',persistent_profile_changed=False,
        controlled_ROI_PC_diagnostic_passed=True,target_measurements_on_LCD=False,
        parent_checkpoint='results/p67-final-20261026T021904Z/report.json',
        handoff='docs/handoff/RESUME-P68-20261026.md',checkpoint=rel(out/'checkpoint.zip'))
    # Derive scores rather than relying on a narrative total.
    groups=[g for g in v['segments'] if g['name']!='tone']
    if (sum(g['updates'] for g in groups)!=57 or sum(g['classified'] for g in groups)!=55
        or sum(g['correct'] for g in groups)!=55):raise ValueError('score narrative differs')
    write(out/'acceptance.json',status)
    write(ROOT/'results/p68-active.json',dict(status=status['status'],report=rel(out/'acceptance.json'),
        report_sha256=sha(out/'acceptance.json'),handoff=status['handoff'],checkpoint=status['checkpoint']))
    inputs=[ROOT/'START-HERE.md',ROOT/'docs/WORKFLOW-NEXT-20261024.md',ROOT/status['handoff'],
        ROOT/'docs/experiments/EXP-P68-RF-dashboard-20261026.md',human,link,
        ROOT/'results/p68-active.json',out/'acceptance.json']
    inputs.extend(ROOT/'experiments'/name for name in ('p68_rf_dashboard_trial.py','p68_evidence.py','p68_review_rf.py','p68_finalize.py'))
    for report in (trial,review,ROOT/'results/p59-status-20261026T022100731203Z/report.json',ROOT/t['source_upload']):
        inputs.extend(p for p in report.parent.rglob('*') if p.is_file())
    # Keep exact orchestration/decode/math code used for this stage alongside
    # its parent binary checkpoint; no need to duplicate the whole old project.
    for name in ('host/board_control.py','src/rfsig/board_session.py',
        'src/rfsig/bandwidth.py','src/rfsig/spectrum.py','src/rfsig/rf_ai_calibration.py',
        'src/rfsig/trainable_cnn.py','src/rfsig/cnn_quantization.py',
        'experiments/p67_board_trial.py','experiments/p35_uart_files.py','experiments/p46_console.py',
        'experiments/p52_ram.py','experiments/p36_retrieve_file.py','experiments/p37_review_archives.py',
        'experiments/p48_verify_units.py','embedded/arm_panel/font8x12.h'):
        inputs.append(ROOT/name)
    inputs=sorted(set(inputs));manifest={rel(p):dict(bytes=p.stat().st_size,sha256=sha(p)) for p in inputs}
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
    write(out/'report.json',dict(status='passed_P68_increment_zip_CRC_all_members_SHA',
        acceptance=rel(out/'acceptance.json'),acceptance_sha256=sha(out/'acceptance.json'),
        checkpoint=rel(archive),checkpoint_bytes=archive.stat().st_size,checkpoint_sha256=sha(archive),
        manifest=rel(out/'manifest.json'),manifest_sha256=sha(out/'manifest.json'),verified_members=len(manifest),board_operations=False))
    print(out);print(status['status'])
if __name__=='__main__':main()
