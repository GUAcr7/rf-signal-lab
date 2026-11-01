"""Archive the P69 milestone before any persistent startup changes."""
from datetime import datetime,timezone
from pathlib import Path
import hashlib,zipfile
from p45_checkpoint import ROOT,read,write,sha,rel

def main():
    review=ROOT/'results/p69-board-review-20261026T030150Z/report.json';v=read(review)
    trial=ROOT/v['trial'];t=read(trial)
    if v['status']!='passed_P69_native_ROI_RF_AI_pixels_and_invalidation' or sha(trial)!=v['trial_sha256'] or not t['serial_closed']:raise ValueError('P69 reviewed stopped trial required')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p69-final-%Y%m%dT%H%M%SZ');out.mkdir()
    write(out/'human.json',dict(source='direct_user_answer',user_answer='只看到unavailable或已停止，未观察到数值',numeric_visibility_confirmed=False))
    acceptance=dict(status='passed_P69_RF_LCD_ROI_metrics_and_invalidation',review=rel(review),review_sha256=sha(review),
        trial=rel(trial),trial_sha256=sha(trial),build=v['build'],build_sha256=v['build_sha256'],binary_sha256=v['binary_sha256'],
        TX_boot=t['after_TX']['boot_id'],RX_boot=t['after_RX']['boot_id'],TX_stopped=True,RX_stopped=True,serial_closed=True,
        powered_off=False,persistent_profile_changed=False,AI_accuracy_newly_measured=False,numeric_visibility_confirmed=False,
        display_updates=v['display_updates'],valid_measurements=v['valid_measurements'],invalid_measurements=v['invalid_measurements'],
        handoff='docs/handoff/RESUME-P69-20261026.md',checkpoint=rel(out/'checkpoint.zip'),parent='results/p68-final-20261026T023906Z/report.json')
    write(out/'acceptance.json',acceptance)
    write(ROOT/'results/p69-active.json',dict(status=acceptance['status'],report=rel(out/'acceptance.json'),report_sha256=sha(out/'acceptance.json'),handoff=acceptance['handoff'],checkpoint=acceptance['checkpoint']))
    paths=[ROOT/'START-HERE.md',ROOT/'docs/WORKFLOW-NEXT-20261024.md',ROOT/acceptance['handoff'],ROOT/'docs/experiments/EXP-P69-LCD-metrics-20261026.md',ROOT/'results/p69-active.json',out/'human.json',out/'acceptance.json']
    for folder in (review.parent,trial.parent,(ROOT/v['build']).parent,ROOT/'results/p69-offline-20261026T025002Z',(ROOT/v['base_review']).parent):
        paths.extend(p for p in folder.rglob('*') if p.is_file())
    for folder in (ROOT/'results').glob('p69-trial-code-*'):paths.extend(p for p in folder.rglob('*') if p.is_file())
    paths.extend((ROOT/'experiments').glob('p69_*.py'))
    paths.extend((ROOT/'embedded/arm_live_panel_p69').glob('*.h'))
    paths += [ROOT/'tests/test_roi_metrics_p69.py',ROOT/'results/p69-math-tests-20261026.xml',ROOT/'results/p69-math-first-harness-error-20261026.xml']
    paths=sorted(set(paths));manifest={rel(p):dict(bytes=p.stat().st_size,sha256=sha(p)) for p in paths}
    write(out/'manifest.json',dict(schema='rfsig.recovery_increment.v1',parent=acceptance['parent'],files=manifest))
    archive=out/'checkpoint.zip'
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in paths:z.write(p,rel(p))
        z.write(out/'manifest.json',rel(out/'manifest.json'))
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:raise ValueError('ZIP CRC failed')
        for name,item in manifest.items():
            data=z.read(name)
            if len(data)!=item['bytes'] or hashlib.sha256(data).hexdigest()!=item['sha256']:raise ValueError('ZIP member differs')
    write(out/'report.json',dict(status='passed_P69_recovery_zip_CRC_all_SHA',checkpoint=rel(archive),checkpoint_bytes=archive.stat().st_size,checkpoint_sha256=sha(archive),verified_members=len(paths),board_operations=False))
    print(out)
if __name__=='__main__':main()
