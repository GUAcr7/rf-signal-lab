"""Save P81 human rehearsal evidence; no hardware operations or frozen edits."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import statistics
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'experiments'), str(ROOT / 'host'), str(ROOT / 'src')]
from p80_review_latency import timings


def read(path):
    return json.loads(path.read_text('utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    screen_path = ROOT / 'results/p80-screen-control-20261027T141654Z/report.json'
    archive_path = ROOT / 'results/p59-p79-session-archive-20261027T142252005759Z/report.json'
    review_path = ROOT / 'results/p79-review-20261027T142421Z/report.json'
    screen, archive, review = map(read, (screen_path, archive_path, review_path))
    assert screen['input_origin'] == 'human_finger' and screen['serial_closed']
    assert screen['status'] == 'passed_P79_physical_screen_RF_presets_and_cleanup'
    assert screen['required_presets_and_stop_completed'] and screen['fast_control']
    assert archive['status'] == 'passed_P79_stopped_RX_full_history_archived'
    assert archive['serial_closed'] and archive['RX_stopped'] and archive['TX_stopped']
    assert archive['screen_sha256'] == sha(screen_path)
    assert review['human_three_preset_rehearsal'] and all(g['passed'] for g in review['gates'])
    assert review['archive_sha256'] == sha(archive_path)
    rows = timings(screen)
    latency = {}
    for action in ('check', 'start', 'stop'):
        samples = [x['completion_s'] for x in rows if x['action'] == action]
        latency[action] = dict(samples=len(samples), median_s=statistics.median(samples),
                               minimum_s=min(samples), maximum_s=max(samples))
    now = datetime.now(timezone.utc)
    out = ROOT / 'results' / now.strftime('p81-final-%Y%m%dT%H%M%SZ')
    out.mkdir()
    relative = lambda p: p.resolve().relative_to(ROOT).as_posix()
    report = dict(status='passed_P81_human_screen_RF_rehearsal_saved', created_utc=now.isoformat(),
                  screen_report=relative(screen_path), screen_sha256=sha(screen_path),
                  archive=relative(archive_path), archive_sha256=sha(archive_path),
                  review=relative(review_path), review_sha256=sha(review_path),
                  human_three_preset_rehearsal=True, latency_rows=rows, latency=latency,
                  RF_groups=review['groups'], display_updates=review['display_updates'],
                  elapsed_software_s=review['elapsed_software_s'],
                  TX_stopped=True, RX_stopped=True, DDS_digital_zero=True, handles_released=True,
                  user_feedback=dict(buttons_faster=True, TX_RX_display_normal=True,
                                     final_STOP_returned_IDLE=True),
                  missing_STOP_packets_on_first_attempts=True,
                  missing_STOP_root_cause='unconfirmed; no raw STOP packet, final deliberate touch succeeded',
                  direct_P201_UART=False, standalone_without_PC=False,
                  new_independent_AI_accuracy=False, persistent_board_changes=False,
                  reboots_issued=0, boards_powered=True,
                  parent=read(ROOT / 'results/p80-active.json'),
                  next_tasks=['archive teammate final HMI/TFT',
                              'verify independent P201 UART physical loopback before screen wiring',
                              'move control to P201 and verify persistent boot recovery'])
    write(out / 'report.json', report)
    handoff = 'docs/handoff/RESUME-P81-20261027.md'
    write(ROOT / 'results/p81-active.json', dict(status=report['status'], report=relative(out / 'report.json'),
          report_sha256=sha(out / 'report.json'), handoff=handoff,
          checkpoint=relative(out / 'checkpoint.zip'), acceptance=relative(out / 'acceptance.json')))
    status_path = ROOT / 'TX-SOURCE-STATUS.json'
    current = read(status_path)
    current.update(updated=now.isoformat(), updated_note='P81 complete human fast screen rehearsal and full receiver audit passed; TX/RX stopped.',
                   status=report['status'], status_note='人工三类屏控及发射中STOP已验收；收发停、连接释放，独立直连待完成。',
                   p81_current=read(ROOT / 'results/p81-active.json'))
    write(status_path, current)
    paths = set()
    def add(path):
        path = path.resolve()
        path.relative_to(ROOT)
        if path.is_dir():
            paths.update(p.resolve() for p in path.rglob('*') if p.is_file())
        else:
            assert path.is_file(), path
            paths.add(path)
    for p in (screen_path.parent, archive_path.parent, review_path.parent):
        add(p)
    prepare = ROOT / 'results/p79-prepare-session-20261027T141434Z/report.json'
    pilot = ROOT / 'results/p79-cancel-trial-20261027T141611Z/report.json'
    add(prepare.parent)
    add(pilot.parent)
    for step in read(prepare)['steps']:
        add((ROOT / step['report']).parent)
    add((ROOT / read(pilot)['job']['report']).parent)
    for job in screen['jobs']:
        add((ROOT / job['report']).parent)
    add((ROOT / screen['startup_report']).parent)
    for name in ('START-HERE.md', 'TX-SOURCE-STATUS.json', handoff,
                 'docs/experiments/EXP-P81-manual-screen-rehearsal-20261027.md',
                 'docs/source-screen-control.md', 'experiments/p81_save_manual.py',
                 'results/p81-active.json', 'results/p80-active.json',
                 'configs/receiver-profile.json', 'configs/board-connections.json'):
        add(ROOT / name)
    add(out / 'report.json')
    manifest = {relative(p): sha(p) for p in sorted(paths)}
    write(out / 'manifest.json', manifest)
    with zipfile.ZipFile(out / 'checkpoint.zip', 'x', zipfile.ZIP_DEFLATED) as z:
        for p in sorted(paths):
            z.write(p, relative(p))
        z.write(out / 'manifest.json', relative(out / 'manifest.json'))
    with zipfile.ZipFile(out / 'checkpoint.zip') as z:
        assert z.testzip() is None
        assert len(z.namelist()) == len(set(z.namelist())) == len(paths) + 1
        for name, digest in manifest.items():
            assert hashlib.sha256(z.read(name)).hexdigest() == digest
    write(out / 'acceptance.json', dict(status='passed_P81_checkpoint_CRC_unique_entries_SHA256',
          files=len(paths), zip_bytes=(out / 'checkpoint.zip').stat().st_size,
          zip_sha256=sha(out / 'checkpoint.zip'), manifest_sha256=sha(out / 'manifest.json'),
          parent_checkpoint_required=True, hardware_operations=False))
    print(out)
    print(report['status'])


if __name__ == '__main__':
    main()
