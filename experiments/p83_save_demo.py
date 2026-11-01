"""Save the observed P83 demo with explicit partial coverage; no hardware I/O."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def read(p):
    return json.loads(p.read_text('utf-8'))


def write(p, v):
    p.write_text(json.dumps(v, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    outer = ROOT / 'results/p83-visual-demo-20261028/report.json'
    initial = read(outer)
    assert initial['status'] == 'running_P83_manual_visual_demo'
    review_path = ROOT / 'results/p83-review-20261028T113315Z/report.json'
    review = read(review_path)
    archive_path = ROOT / review['archive']
    archive = read(archive_path)
    screen_path = ROOT / review['screen']
    screen = read(screen_path)
    assert review['status'] == 'passed_P83_observed_sources_and_cleanup_partial_coverage'
    assert all(g['passed'] for g in review['gates'])
    assert not review['complete_three_class_and_STOP']
    assert sha(archive_path) == review['archive_sha256'] and sha(screen_path) == review['screen_sha256']
    assert archive['TX_stopped'] and archive['RX_stopped'] and archive['serial_closed'] and screen['serial_closed']
    assert archive['after_TX']['DDS_raw'] == archive['after_TX']['DDS_scale'] == ['0'] * 8
    now = datetime.now(timezone.utc)
    out = ROOT / 'results' / now.strftime('p83-final-%Y%m%dT%H%M%SZ')
    out.mkdir()
    rel = lambda p: p.resolve().relative_to(ROOT).as_posix()
    report = dict(initial)
    report.update(status='saved_P83_BPSK_visual_demo_partial_coverage', saved_utc=now.isoformat(),
                  all_completion_claims_pending=False, user_feedback='全部正常，演示完成',
                  review=rel(review_path), review_sha256=sha(review_path),
                  archive=rel(archive_path), archive_sha256=sha(archive_path),
                  screen_sha256=sha(screen_path), observed_natural_signals=review['observed_natural_signals'],
                  missing_natural_signals=review['missing_natural_signals'],
                  actual_inflight_STOP=review['actual_inflight_STOP'],
                  complete_three_class_and_STOP=False, groups=review['groups'],
                  display_updates=review['display_updates'], elapsed_software_s=review['elapsed_software_s'],
                  parent_full_three_class_acceptance=read(ROOT / 'results/p81-active.json'),
                  TX_stopped=True, RX_stopped=True, DDS_digital_zero=True, all_handles_released=True,
                  boards_shutdown=False, persistent_board_changes=False, TX2_enabled=False,
                  captured_phone_video_file=False,
                  TX_boot=archive['after_TX']['boot_id'], RX_boot=archive['after_RX']['boot_id'])
    write(out / 'report.json', report)
    write(outer.parent / 'initial-session.json', initial)
    write(outer, report)
    pointer = dict(status=report['status'], report=rel(out / 'report.json'), report_sha256=sha(out / 'report.json'),
                   handoff='docs/handoff/RESUME-P83-20261028.md', checkpoint=rel(out / 'checkpoint.zip'),
                   acceptance=rel(out / 'acceptance.json'))
    write(ROOT / 'results/p83-active.json', pointer)
    status = read(ROOT / 'TX-SOURCE-STATUS.json')
    status.update(updated=now.isoformat(), status=report['status'], p83_current=pointer,
                  updated_note='P83 observed BPSK and visual feedback saved; missing QPSK/16QAM/STOP preserved; TX/RX stopped.',
                  status_note='本轮BPSK通过并已停止保存；三类及STOP完整验收仍引用P81，本轮不冒充。')
    write(ROOT / 'TX-SOURCE-STATUS.json', status)
    paths = set()

    def add(p):
        p = p.resolve()
        p.relative_to(ROOT)
        assert p.exists(), p
        paths.update(q.resolve() for q in p.rglob('*') if q.is_file()) if p.is_dir() else paths.add(p)

    for p in (screen_path.parent, archive_path.parent, review_path.parent, outer.parent):
        add(p)
    for name in ('prepare', 'pilot'):
        p = ROOT / initial[name]
        add(p.parent)
        source = read(p)
        for step in source.get('steps', []):
            add((ROOT / step['report']).parent)
        if 'job' in source:
            add((ROOT / source['job']['report']).parent)
    for job in screen['jobs']:
        add((ROOT / job['report']).parent)
    add((ROOT / screen['startup_report']).parent)
    for name in ('START-HERE.md', 'TX-SOURCE-STATUS.json', pointer['handoff'],
                 'docs/experiments/EXP-P83-visual-demo-20261028.md', 'docs/demo-visual-20261028.md',
                 'docs/design/contest-scope-20261028.md', 'docs/design/video-rf-comparison-20261028.md',
                 'docs/experiments/EXP-P82-tx2-readonly-20261028.md', 'docs/experiments/EXP-RESUME-20261028.md',
                 'experiments/p83_save_demo.py', 'experiments/p83_review_visual_demo.py',
                 'experiments/p82_tx2_readonly.py', 'run-source-screen.cmd', 'configs/receiver-profile.json',
                 'configs/board-connections.json', 'results/p83-active.json', 'results/p81-active.json',
                 'results/resume-20261028', 'results/contest-rules-20261028',
                 'results/p59-p82-TX2-readonly-20261028T105600151365Z',
                 'results/p59-p82-TX2-readonly-20261028T105753420323Z'):
        add(ROOT / name)
    add(out / 'report.json')
    manifest = {rel(p): sha(p) for p in sorted(paths)}
    write(out / 'manifest.json', manifest)
    with zipfile.ZipFile(out / 'checkpoint.zip', 'x', zipfile.ZIP_DEFLATED) as z:
        for p in sorted(paths):
            z.write(p, rel(p))
        z.write(out / 'manifest.json', rel(out / 'manifest.json'))
    with zipfile.ZipFile(out / 'checkpoint.zip') as z:
        assert z.testzip() is None
        assert len(z.namelist()) == len(set(z.namelist())) == len(paths) + 1
        for name, digest in manifest.items():
            assert hashlib.sha256(z.read(name)).hexdigest() == digest
    write(out / 'acceptance.json', dict(status='passed_P83_saved_checkpoint_CRC_SHA256_partial_demo_scope',
          files=len(paths), zip_bytes=(out / 'checkpoint.zip').stat().st_size, zip_sha256=sha(out / 'checkpoint.zip'),
          manifest_sha256=sha(out / 'manifest.json'), parent_P81_required=True,
          complete_three_class_and_STOP=False, hardware_operations=False))
    print(out)
    print(report['status'])


if __name__ == '__main__':
    main()
