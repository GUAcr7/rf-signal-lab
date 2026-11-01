"""Freeze P59/P60 evidence, current handoff and recoverable checkpoint. No board IO."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
from urllib.parse import unquote
import xml.etree.ElementTree as ET

from p45_checkpoint import ROOT, read, write, sha, rel, checkpoint
from rfsig.board_session import require_rx_control, require_tx_off


def main():
    out = ROOT / 'results/p59-final-20261025T030227Z'
    if not (out / 'before/START-HERE.md').is_file() or (out / 'report.json').exists():
        raise ValueError('Prepared backup directory required; never overwrite final record')
    paths = dict(demo=ROOT / 'results/p59-demo-20261025T025236599641Z/report.json',
                 archive=ROOT / 'results/p59-archive-20261025T025904857628Z/report.json',
                 status=ROOT / 'results/p59-status-20261025T030607484086Z/report.json',
                 UART=ROOT / 'results/p60-uart-comparison-20261025T025752Z/report.json',
                 tests=ROOT / 'results/p59-release-tests-20261025.xml',
                 prior_boot_tests=ROOT / 'results/p59-control-tests-20261025.xml')
    demo, arc, state, uart = [read(paths[k]) for k in ('demo', 'archive', 'status', 'UART')]
    if demo['status'] != 'passed_P59_fixed_entry_full_short_demo_RX_TX_stopped':
        raise ValueError('Demo incomplete')
    for step in demo['steps']:
        if not step['passed'] or sha(ROOT / step['report']) != step['report_sha256']:
            raise ValueError('Demo provenance changed')
    if arc['status'] != 'passed_P59_archive' or arc['demo_sha256'] != sha(paths['demo']):
        raise ValueError('Complete matching byte archive required')
    for name, digest in arc['archived_members_sha256'].items():
        if sha(paths['archive'].parent / 'files' / name) != digest:
            raise ValueError('Archived member changed')
    if state['status'] != 'passed_P59_status':
        raise ValueError('Current read-only status incomplete')
    rx, tx = state['boards']['RX'], state['boards']['TX']
    require_rx_control(rx, running=False); require_tx_off(tx)
    if rx['boot_id'] != demo['final_RX']['boot_id'] or tx['boot_id'] != demo['final_TX']['boot_id']:
        raise ValueError('Board boot changed before handoff')
    if uart['deployable'] or not uart['critical_endpoint_multisets_identical']:
        raise ValueError('Unexpected UART comparison result')
    root = ET.parse(paths['tests']).getroot()
    cases = list(root.iter('testcase'))
    if len(cases) != 32 or any(list(c.iter('failure')) or list(c.iter('error')) for c in cases):
        raise ValueError('Final 32 control checks required')
    old_source = read(ROOT / 'TX-SOURCE-STATUS.json')
    old_snapshot = read(out / 'before/TX-SOURCE-STATUS.json')
    if old_source != old_snapshot:
        raise ValueError('Status metadata changed concurrently; reconcile instead of overwrite')
    record = dict(status='passed_P59_fixed_PC_control_short_RF_demo_archived_P60_review_pending_UART_deploy',
        created_utc=datetime.now(timezone.utc).isoformat(),
        reports={k: dict(path=rel(p), sha256=sha(p)) for k, p in paths.items()},
        RX_boot=rx['boot_id'], TX_boot=tx['boot_id'],
        RX_and_TX_idle=True, serial_closed=True, board_shutdown=False,
        persistent_P57_AI_selected=rx['profile_verified'],
        model_independent_score_unchanged='P52 INT8 52/54 controlled test',
        short_demo_elapsed_s=arc['elapsed_software_s'], history_updates=arc['history_updates'],
        full_history_deployment_scores=arc['full_history_deployment_scores'],
        control_tests=32, human_visual_confirmed_this_round=False,
        IQ_replay_performed=False, new_cold_cycle_verified=False,
        new_ten_minute_verified=False, PL_or_driver_changes=False,
        PHY_RF_attribute_writes=False, DDS_zero_selection=True,
        W0_fixed_PC_entry_verified=True, W0_standalone_complete=False,
        W1_screen_in_hand=True, screen_model=None, UART_deployed=False,
        UART_critical_endpoint_comparison=dict(current=67, historical=67, added=0),
        next_tasks=['Review inherited DMA CDC handshakes, external timing and UART initialization',
                    'Identify exact screen, logic voltage, supply and protocol before connection',
                    'Prepare recoverable UART boot bundle and validate physical loopback',
                    'Integrate screen controls and persistent source recovery'],
        checkpoint='results/p59-checkpoint-20261025T030227Z/report.json')
    sources = ['host/board_control.py', 'src/rfsig/board_session.py', 'run-board-control.cmd',
               'tests/test_board_session.py', 'tests/test_board_control_entry.py',
               'experiments/p59_archive_session.py', 'experiments/p60_uart_detail_review.py',
               'experiments/p60_compare_uart_cdc.py', 'experiments/p59_finalize.py']
    record['current_sources_sha256'] = {name: sha(ROOT / name) for name in sources}
    docs = ['START-HERE.md', 'docs/WORKFLOW-NEXT-20261024.md', 'docs/board-control.md',
            'docs/experiments/EXP-P59-fixed-control-20261025.md',
            'docs/experiments/EXP-P60-UART-review-20261025.md', 'docs/handoff/RESUME-P59-20261025.md']
    checked = []
    for name in docs:
        path = ROOT / name
        for href in re.findall(r'\[[^\]]*\]\(([^)]+)\)', path.read_text('utf-8')):
            if href.startswith(('http://', 'https://', '#')):
                continue
            target = (path.parent / unquote(href.split('#')[0])).resolve()
            if not target.is_file():
                raise ValueError('Broken document link: ' + name + ': ' + href)
            checked.append([name, href])
    record['local_document_links_verified'] = len(checked)
    record['documents_sha256'] = {name: sha(ROOT / name) for name in docs}
    for name in sources + docs:
        target = out / 'current-files' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
        if sha(target) != sha(ROOT / name):
            raise ValueError('Snapshot mismatch')
    write(out / 'report.json', record)
    active = dict(status=record['status'], report=rel(out / 'report.json'),
        report_sha256=sha(out / 'report.json'), expected_boot=rx['boot_id'],
        TX_expected_boot=tx['boot_id'], RX_and_TX_idle=True, serial_closed=True,
        board_shutdown=False, persistent_AI_selected=True,
        workflow='docs/WORKFLOW-NEXT-20261024.md', handoff='docs/handoff/RESUME-P59-20261025.md',
        checkpoint=record['checkpoint'], UART_deployed=False, screen_model_pending=True)
    write(ROOT / 'results/p59-active.json', active)
    write(ROOT / 'results/p60-uart-active.json', dict(status=uart['status'],
          report=rel(paths['UART']), report_sha256=sha(paths['UART']), deployable=False))
    old_source['p59_current'] = active
    write(ROOT / 'TX-SOURCE-STATUS.json', old_source)
    packet = checkpoint('p59-checkpoint', {'final': out / 'report.json', **paths},
                        destination=ROOT / 'results/p59-checkpoint-20261025T030227Z')
    result = read(packet)
    if not result['all_member_SHA_verified']:
        raise ValueError('Checkpoint did not verify')
    print(out, flush=True)
    print(result['status'], flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
