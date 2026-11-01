"""Save the P70 cold-ready state, including the honest failed AI regression."""
from datetime import datetime,timezone
from pathlib import Path
import hashlib,zipfile
from p45_checkpoint import ROOT,read,write,sha,rel

def main():
    warm=ROOT/'results/p70-boot-20261026T031221Z/report.json';halt=ROOT/'results/p59-p70-halt-20261026T032913743165Z/report.json'
    review=ROOT/'results/p70-review-20261026T033200Z/report.json';w,h,v=read(warm),read(halt),read(review)
    config=ROOT/'configs/receiver-profile.json';selection=read(config)
    if (w['status']!='passed_P70_warm_boot_autonomous_ROI_display' or h['status']!='passed_P70_data_archived_System_halted'
        or not h['halt_observed'] or not h['serial_closed'] or not h['prior_archive_verified']
        or v['all_RF_AI_gates_passed'] or not v['cleanup_passed'] or selection['report_sha256']!=sha(warm)):
        raise ValueError('exact warm/halted/archive/known-failure state required')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p70-final-%Y%m%dT%H%M%SZ');out.mkdir()
    acceptance=dict(status='P70_warm_startup_verified_halted_cold_pending_AI_issue_open',
        warm_profile=rel(warm),warm_profile_sha256=sha(warm),halt=rel(halt),halt_sha256=sha(halt),
        review=rel(review),review_sha256=sha(review),selected_directory=w['installed_directory'],
        configuration=rel(config),configuration_sha256=sha(config),
        TX_boot=w['TX_expected_boot'],RX_last_boot=h['expected_boot'],TX_stopped=True,RX_running=False,RX_halted=True,
        serial_closed=True,true_power_cycle_verified=False,physical_power_removed=False,
        metrics_on_LCD=True,warm_autonomous_startup_verified=True,all_AI_regression_gates_passed=False,
        known_issue='16QAM stable complete history accepted 7/12; 5 uncertain; model/threshold unchanged; investigate independently',
        handoff='docs/handoff/RESUME-P70-20261026.md',checkpoint=rel(out/'checkpoint.zip'),
        parent='results/p69-final-20261026T031117Z/report.json')
    write(out/'acceptance.json',acceptance)
    pointer=dict(status=acceptance['status'],report=rel(out/'acceptance.json'),report_sha256=sha(out/'acceptance.json'),
        handoff=acceptance['handoff'],checkpoint=acceptance['checkpoint'],RX_running=False,RX_halted=True,true_power_cycle_verified=False)
    write(ROOT/'results/p70-active.json',pointer)
    source_status=ROOT/'TX-SOURCE-STATUS.json';source=read(source_status)
    source.update(status=acceptance['status'],authoritative_current_field='p70_current',p70_current=pointer);write(source_status,source)
    paths=[out/'acceptance.json',ROOT/'START-HERE.md',source_status,config,ROOT/'results/p70-active.json',
        ROOT/'docs/experiments/EXP-P70-persistent-metrics-20261026.md',ROOT/acceptance['handoff'],ROOT/'docs/WORKFLOW-NEXT-20261024.md',
        ROOT/'host/board_control.py',ROOT/'src/rfsig/receiver_profile.py',ROOT/'tests/test_receiver_profile_p70.py',ROOT/'tests/test_p70_archive_marker.py']
    paths.extend((ROOT/'experiments').glob('p70_*.py'))
    for p in (ROOT/'results').glob('p70-*'):
        if p==out:continue
        paths.extend([p] if p.is_file() else [x for x in p.rglob('*') if x.is_file()])
    folders={halt.parent,(ROOT/v['archive']).parent,ROOT/'results/p59-p70-halt-20261026T032359473867Z'}
    demo=ROOT/v['demo'];d=read(demo);folders.add(demo.parent)
    for step in d['steps']:folders.add((ROOT/step['report']).parent)
    for folder in folders:paths.extend(p for p in folder.rglob('*') if p.is_file())
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
            if len(data)!=item['bytes'] or hashlib.sha256(data).hexdigest()!=item['sha256']:raise ValueError('ZIP member changed')
    write(out/'report.json',dict(status='passed_P70_cold_ready_increment_CRC_SHA_including_known_AI_failure',
        checkpoint=rel(archive),checkpoint_bytes=archive.stat().st_size,checkpoint_sha256=sha(archive),verified_members=len(paths),board_operations=False))
    print(out)
if __name__=='__main__':main()
