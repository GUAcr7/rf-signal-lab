from pathlib import Path
from datetime import datetime, timezone, timedelta
import hashlib
import json
import re
import shutil
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[2]
DEST = Path(__file__).resolve().parent
DOCS = [
    Path('START-HERE.md'),
    Path('docs/WORKFLOW-NEXT-20261024.md'),
    Path('docs/experiments/EXP-WORKFLOW-20261024.md'),
]

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

links = []
for relative in DOCS:
    path = ROOT / relative
    content = path.read_text(encoding='utf-8-sig')
    assert '\ufffd' not in content, str(relative)
    for href in re.findall(r'\[[^\]]*\]\(([^)]+)\)', content):
        if href.startswith(('https://', 'http://', '#')):
            continue
        target = (path.parent / unquote(href.split('#')[0])).resolve()
        assert target.is_file(), (str(relative), href)
        links.append({'source': relative.as_posix(), 'target': href, 'exists': True})

before = (DEST / 'START-HERE.before.md').read_text(encoding='utf-8-sig')
after = (ROOT / 'START-HERE.md').read_text(encoding='utf-8-sig')
old_body = before.split('\n\n', 1)[1]
assert after.endswith(old_body), 'Existing P58 handoff text changed'

active_path = ROOT / 'results/p58-active.json'
active = json.loads(active_path.read_text(encoding='utf-8-sig'))
final_path = ROOT / active['report']
assert sha(final_path) == active['report_sha256'], 'P58 report hash mismatch'
assert (ROOT / active['checkpoint']).is_file()
uart_path = ROOT / 'results/p201-uart-active.json'
uart = json.loads(uart_path.read_text(encoding='utf-8-sig'))
assert uart['deployable'] is False and uart['physical_UART_tested'] is False

members = []
for relative in DOCS:
    source = ROOT / relative
    snapshot = DEST / 'snapshots' / relative
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, snapshot)
    expected = sha(source)
    assert sha(snapshot) == expected
    members.append({'source': relative.as_posix(), 'snapshot': snapshot.relative_to(DEST).as_posix(),
                    'bytes': source.stat().st_size, 'sha256': expected})

manifest = '\n'.join(item['sha256'] + '  ' + item['snapshot'] for item in members) + '\n'
(DEST / 'SHA256SUMS').write_bytes(manifest.encode('utf-8'))
record = {
    'status': 'passed_workflow_documents_local_links_and_snapshot_SHA_verified',
    'recorded_local': datetime.now(timezone(timedelta(hours=8))).isoformat(),
    'timezone': 'Asia/Shanghai',
    'purpose': 'User requested a new prioritized working workflow; documentation only.',
    'board_operations': False,
    'hardware_state_rechecked': False,
    'code_configuration_or_raw_experiment_changes': False,
    'original_P58_handoff_body_preserved': True,
    'local_link_count': len(links),
    'local_links': links,
    'documents': members,
    'START_HERE_backup_sha256': sha(DEST / 'START-HERE.before.md'),
    'P58_active_sha256': sha(active_path),
    'P58_final_report_sha256_matches_active': True,
    'UART_candidate_deployable': uart['deployable'],
    'UART_candidate_physical_tested': uart['physical_UART_tested'],
    'archive_scope': 'Three current documents plus pre-edit START-HERE; not a full project checkpoint.',
    'verification_script_sha256': sha(Path(__file__)),
}
(DEST / 'report.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'status': record['status'], 'local_links': len(links),
                  'documents': len(members), 'report': str(DEST / 'report.json')}, ensure_ascii=False))
