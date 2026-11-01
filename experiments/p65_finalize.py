"""Freeze P64/P65 recovery work including verified editor environment recovery."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from rfsig.board_session import require_rx_control, require_tx_off, rx_cleanup_confirmed


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text('utf-8-sig'))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def rel(path):
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def main():
    evidence = dict(
        source='results/p59-prepare-source-20261025T112330725700Z/report.json',
        start='results/p59-start-20261025T120321232755Z/report.json',
        stop='results/p59-stop-20261025T120418974164Z/report.json',
        archive='results/p59-p65-archive-stopped-20261025T122532907857Z/report.json',
        editor='results/p65-editor-unpack-20261025T112418Z/report.json',
        environment='results/p65-environment-20261025T123705Z/report.json',
        install='results/p65-netfx3-offline-20261025T125224Z/report.json',
        editor_launch='results/p65-editor-verify-20261025T125645Z/report.json',
        tests='results/p65-control-tests-20261025.xml')
    data = {key: read(ROOT / value) for key, value in evidence.items() if value.endswith('.json')}
    for key in ('source', 'start', 'stop', 'archive'):
        if not data[key]['status'].startswith('passed_') or not data[key]['serial_closed']:
            raise ValueError('Incomplete board step: ' + key)
    stop, archive = data['stop'], data['archive']
    final_rx, final_tx = archive['after_RX'], archive['boards']['TX']
    require_rx_control(final_rx, running=False)
    require_tx_off(final_tx)
    if final_rx['boot_id'] != stop['after_RX']['boot_id']:
        raise ValueError('Receiver boot changed')
    if archive['stopped_report_sha256'] != sha(ROOT / evidence['stop']):
        raise ValueError('Archive stop binding changed')
    for name, wanted in stop['controller_inputs_sha256'].items():
        if sha(ROOT / name) != wanted:
            raise ValueError('Tested controller input changed: ' + name)
    if archive['history_updates'] != 113 or archive['state_counts'] != {'CALIBRATION_REQUIRED': 112, 'STOPPED': 1}:
        raise ValueError('Unexpected uncalibrated session history')
    if not rx_cleanup_confirmed(final_rx['summary']):
        raise ValueError('Native cleanup incomplete')
    for name, wanted in archive['archived_members_sha256'].items():
        file = (ROOT / evidence['archive']).parent / 'files' / name
        if sha(file) != wanted:
            raise ValueError('Saved RX member changed')
    cases = list(ET.parse(ROOT / evidence['tests']).getroot().iter('testcase'))
    if len(cases) != 58 or any(c.findall('failure') or c.findall('error') or c.findall('skipped') for c in cases):
        raise ValueError('Expected 58 passed checks')
    env = data['environment']
    if env['status'] != 'matching_NetFx3_source_saved_online_install_not_yet_verified':
        raise ValueError('Environment snapshot contract changed')
    package = Path(env['package']['path'])
    if sha(package) != env['package']['sha256']:
        raise ValueError('E drive source changed')
    if data['install']['status'] != 'NetFx3_enabled_editor_launch_not_yet_verified' or data['install']['exit_code'] != 0 or data['install']['after']['State'] != 2 or not data['install']['CLR2_DLL_present']:
        raise ValueError('Installation not proven')
    if data['editor_launch']['status'] != 'verified_NetFx3_installed_and_TJC_editor_main_window_open' or not data['editor_launch']['main_window_visually_observed'] or data['editor_launch']['resource_error_dialog_observed']:
        raise ValueError('Editor launch not proven')
    documents = [ROOT / name for name in (
        'START-HERE.md', 'docs/board-control.md',
        'docs/handoff/RESUME-P65-20261025.md',
        'docs/experiments/EXP-P65-COM10-control-20261025.md',
        'docs/handoff/HOLD-P201-JTAG-20261025.md')]
    links = 0
    for doc in documents:
        for target in re.findall(r'\]\(([^)]+)\)', doc.read_text('utf-8')):
            if re.match(r'^[A-Za-z]+:', target) or target.startswith('#'):
                continue
            if not (doc.parent / unquote(target.split('#')[0])).resolve().exists():
                raise ValueError('Broken link: ' + rel(doc) + ' -> ' + target)
            links += 1
    parents = []
    for name in (
        'results/p59-checkpoint-20261025T030227Z/report.json',
        'results/p61-tjc-integration-20261025T034600Z/report.json',
        'results/p62-model-record-20261025T041700Z/report.json',
        'results/p63-final-20261025T053937Z/report.json'):
        p = ROOT / name; prior = read(p)
        if sha(ROOT / prior['archive']['path']) != prior['archive']['sha256']:
            raise ValueError('Parent checkpoint changed')
        parents.append(dict(report=name, sha256=sha(p), archive=prior['archive']))
    out = ROOT / 'results' / datetime.now(timezone.utc).strftime('p65-final-%Y%m%dT%H%M%SZ')
    out.mkdir(exist_ok=False)
    source_status = ROOT / 'TX-SOURCE-STATUS.json'
    (out / 'prior-TX-SOURCE-STATUS.json').write_bytes(source_status.read_bytes())
    active = dict(status='passed_P65_COM10_control_source_restore_RX_stop_editor_ready',
        report=rel(out / 'report.json'), handoff='docs/handoff/RESUME-P65-20261025.md',
        hardware_status=evidence['archive'], TX_boot=final_tx['boot_id'], RX_boot=final_rx['boot_id'],
        TX_stopped=True, RX_stopped=True, serial_closed=True, powered_off=False,
        HMI_compiled=False, TFT_downloaded=False, RF_transmissions=0)
    source_data = read(source_status); source_data['p65_current'] = active
    write(source_status, source_data)
    summary = dict(**active, created_utc=datetime.now(timezone.utc).isoformat(),
        evidence={key: dict(path=value, sha256=sha(ROOT / value)) for key, value in evidence.items()},
        passed_tests=58, archived_RX_AI_rows=113, display_updates=112,
        current_hardware_observation_only=True, ten_minute_acceptance_added=False,
        new_AI_accuracy_claimed=False, new_physical_UART_or_screen_acceptance=False,
        NetFx3_source=env['package'], NetFx3_install_verified=True,
        editor_main_window_verified=True, online_install_may_still_be_running=False, automatic_PC_reboot=False,
        E_drive_editor_and_package_are_external_dependencies=True,
        local_markdown_links_verified=links, parent_checkpoints=parents)
    write(out / 'evidence-summary.json', summary)
    files = set(documents + [source_status, out / 'evidence-summary.json', out / 'prior-TX-SOURCE-STATUS.json'])
    for folder in ('src/rfsig', 'host', 'tests', 'configs', 'docs', 'embedded/source_panel'):
        files.update(p for p in (ROOT / folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    for pattern in ('p64*', 'p65*'):
        files.update(p for p in (ROOT / 'experiments').glob(pattern) if p.is_file())
    explicit = {Path(value).parts[1] for value in evidence.values()}
    explicit.update((
        'p59-status-20261025T111227214214Z', 'p59-status-20261025T111427733546Z',
        'p59-status-20261025T111935156963Z', 'p59-source-off-20261025T112123099177Z',
        'p59-source-active.json'))
    for path in (ROOT / 'results').iterdir():
        if path == out or path.name in ('p65-active.json',):
            continue
        if path.name.startswith(('p64-', 'p65-', 'p59-p64-', 'p59-p65-')) or path.name in explicit:
            # A frozen observation of the online attempt is in environment/.
            # Its working report can change when DISM exits, so omit that live directory.
            if path.name == 'p65-netfx3-system-retry-20261025T121739Z':
                continue
            files.update(path.rglob('*') if path.is_dir() else [path])
    files = {p for p in files if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.zip'}
    manifest = [dict(path=rel(p), bytes=p.stat().st_size, sha256=sha(p)) for p in sorted(files)]
    write(out / 'manifest.json', manifest)
    packed = out / 'p65-recovery-increment.zip'
    with zipfile.ZipFile(packed, 'x', zipfile.ZIP_DEFLATED, compresslevel=3) as z:
        for row in manifest:
            z.write(ROOT / row['path'], row['path'])
        z.write(out / 'manifest.json', 'P65-MANIFEST.json')
    with zipfile.ZipFile(packed) as z:
        if z.testzip() is not None:
            raise ValueError('ZIP CRC failed')
        for row in manifest:
            content = z.read(row['path'])
            if len(content) != row['bytes'] or hashlib.sha256(content).hexdigest() != row['sha256']:
                raise ValueError('Archive member SHA mismatch: ' + row['path'])
    summary['archive'] = dict(path=rel(packed), bytes=packed.stat().st_size, sha256=sha(packed),
                              files=len(manifest), all_member_SHA_and_CRC_verified=True)
    write(out / 'report.json', summary)
    active['report_sha256'] = sha(out / 'report.json')
    write(ROOT / 'results/p65-active.json', active)
    print(out / 'report.json'); print(summary['status']); print('Verified files:', len(manifest))


if __name__ == '__main__':
    main()
