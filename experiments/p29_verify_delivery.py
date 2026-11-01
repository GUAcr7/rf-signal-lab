"""Read-only verify P29 stage results, raw bytes, preserved sources and document links."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    delivery_path = sorted((ROOT / 'results').glob('p29-delivery-*/report.json'))[-1]
    report = json.loads(delivery_path.read_text('utf-8'))
    evidence = report['evidence']
    checked = []
    for name in ['rf_synthesis', 'display_synthesis', 'display_upgrade', 'adi_package', 'sources', 'compiled_audit',
                 'display_clock_refinement', 'display_clock_self_check']:
        path = ROOT / evidence[name]
        stage = json.loads(path.read_text('utf-8'))
        assert stage['status'] == 'passed', (name, stage['status'])
        if 'exit_code' in stage:
            assert stage['exit_code'] == 0, name
        checked.append(dict(name=name, path=str(path), sha256=digest(path)))
    for field in ['RF_transmitted', 'new_bitstream_programmed', 'project_bitstream_generated',
                  'RF_display_integrated', 'display_functional_upgrade_verified', 'real_AI_verified',
                  'lossless_stream_verified', 'python_regression_rerun']:
        assert report[field] is False, field
    work = Path(report['work'])
    for mode in ['rf', 'display']:
        local = delivery_path.parent / f'{mode}-synth.dcp'
        assert local.stat().st_size > 100000, mode
        assert digest(local) == digest(work / local.name), mode
        checked.append(dict(name=local.name, path=str(local), sha256=digest(local)))
    refined = delivery_path.parent/'display-clock-reviewed.dcp'
    assert digest(refined) == digest(work/refined.name)
    checked.append(dict(name=refined.name, path=str(refined), sha256=digest(refined)))
    assert report['refined_display_clock_timing']['checks']['no_clock'] == 0
    assert report['refined_display_clock_timing']['checks']['unconstrained_internal_endpoints'] == 0
    assert report['refined_display_clock_timing']['WHS_ns'] < 0
    assert sum(x['count'] for x in report['cdc_summary']['rf'].values() if x['severity']=='Critical') == 59
    patch = json.loads((ROOT/evidence['hls_vendor_patch']).read_text('utf-8'))
    assert patch['status'] == 'additive_vendor_patch_installed_hash_verified'
    for item in patch['installed']:
        assert digest(Path(item['path'])) == item['sha256']
    for item in patch['baseline']:
        assert digest(Path(item['automg'])) == item['sha256']
    ps = json.loads((ROOT/evidence['PS_generated_comparison']).read_text('utf-8'))['candidates']
    assert (ps['display']['matched'], ps['display']['comparable']) == (5,10)
    assert (ps['rf']['matched'], ps['rf']['comparable']) == (2,9)
    readback_path = ROOT / evidence['rx_readback']
    readback = json.loads(readback_path.read_text('utf-8'))
    raw = readback_path.parent / readback['raw']['file']
    assert raw.stat().st_size == readback['raw']['bytes'] == 65536
    assert digest(raw) == readback['raw']['sha256']
    assert readback['complete_stream_saved'] is False
    metadata = json.loads((raw.parent / 'metadata.json').read_text('utf-8'))
    assert metadata['blocks'] == 16 and metadata['buffer_released'] is True
    assert metadata['RF_attributes_written'] is False
    assert metadata['kept_frames_per_block'] / metadata['dma_frames'] == 0.015625
    for stage in json.loads((ROOT / evidence['adi_package']).read_text('utf-8'))['components']:
        assert digest(Path(stage['path'])) == stage['sha256'], stage['ip']
    files = [ROOT / 'START-HERE.md', ROOT / 'README.md', ROOT / 'docs/implementation-guide.md',
             ROOT / 'docs/experiments/EXP-HW-021-vendor-migration-and-reconnect.md',
             ROOT / 'docs/handoff/RESUME-20261019.md', ROOT / 'docs/design/rf-display-integration-20261019.md']
    broken = []
    links_checked = 0
    for path in files:
        for target in re.findall(r'\]\(([^)]+)\)', path.read_text('utf-8')):
            if target.startswith(('http:', 'https:', '#', 'mailto:')):
                continue
            target = unquote(target.split('#')[0].strip('<>'))
            resolved = path.parent / target
            links_checked += 1
            if not resolved.exists():
                broken.append(dict(document=str(path), target=target))
    assert not broken, broken
    status = json.loads((ROOT / 'TX-SOURCE-STATUS.json').read_text('utf-8'))
    assert status['record'] == 'docs/experiments/EXP-HW-021-vendor-migration-and-reconnect.md'
    assert status['board_runtime_asof_20261019']['cold_start_issue_resolved'] is False
    out = ROOT / 'results' / datetime.now(timezone.utc).strftime('p29-delivery-verification-%Y%m%dT%H%M%SZ')
    out.mkdir(exist_ok=False)
    manifest = dict(status='passed', delivery=str(delivery_path), checked=checked,
                    local_links_checked=links_checked, broken_links=broken,
                    raw_sha256=digest(raw), board_operations=False, regression_rerun=False,
                    source_files=[dict(path=str(p.relative_to(ROOT)), sha256=digest(p)) for p in sorted((ROOT/'experiments').glob('p29_*.py'))],
                    fpga_additions=[dict(path=str(p.relative_to(ROOT)),sha256=digest(p)) for p in
                        [ROOT/'fpga/tb/tb_display_half_clock.sv',ROOT/'fpga/constraints/display_lvds_half_clock.xdc']],
                    documents=[dict(path=str(p.relative_to(ROOT)), sha256=digest(p)) for p in files])
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(out)
    print('passed; source/component/DCP/raw hashes and scope gates; local links', links_checked)


if __name__ == '__main__':
    main()
