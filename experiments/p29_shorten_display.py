"""Copy the failed display build to a short E: path; preserve all original attempts."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def main():
    active_path = ROOT / 'results/p29-active-build.json'
    active = json.loads(active_path.read_text('utf-8'))
    work = Path(active['work'])
    source = work / 'display-v3'
    dest = Path('E:/p29d-1019')
    if dest.exists():
        raise RuntimeError('short build destination already exists; inspect before reuse')
    failure = ROOT / 'results/p29-display-synth-20261019T084313Z/report.json'
    if json.loads(failure.read_text('utf-8'))['status'] != 'failed':
        raise RuntimeError('expected archived failure missing')
    shutil.copytree(source, dest)
    comparisons = []
    for path in source.rglob('*'):
        if path.is_file() and ('.srcs' in str(path) or path.suffix == '.xpr'):
            counterpart = dest / path.relative_to(source)
            before = hashlib.sha256(path.read_bytes()).hexdigest()
            after = hashlib.sha256(counterpart.read_bytes()).hexdigest()
            if before != after:
                raise RuntimeError('copy byte mismatch')
            comparisons.append(dict(path=path.relative_to(source).as_posix(), sha256=before))
    active['display_short_project'] = str(dest / 'axi_video_display.xpr')
    active_path.write_text(json.dumps(active, indent=2) + '\n', encoding='utf-8')
    out = ROOT / 'results' / datetime.now(timezone.utc).strftime('p29-short-display-%Y%m%dT%H%M%SZ')
    out.mkdir(exist_ok=False)
    (out / 'report.json').write_text(json.dumps(dict(status='copied_not_yet_retested',
        original=str(source), destination=str(dest), archived_failure=str(failure),
        reason='Observed HLS IMPL 213-66 destination file path too long; no HDL/constraint changes',
        source_file_hashes=comparisons, originals_removed=False, board_operations=False), indent=2) + '\n', encoding='utf-8')
    print(out)


if __name__ == '__main__':
    main()
