"""Record focused boot-script tests and prove the dangerous test is disabled."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    out = ROOT / 'results' / datetime.now(timezone.utc).strftime('p31-boot-guard-%Y%m%dT%H%M%SZ')
    out.mkdir(exist_ok=False)
    commands = [
        [sys.executable, '-m', 'pytest', 'tests/test_board_rf_readiness.py', '-q'],
        ['wsl.exe', '--exec', '/bin/sh', '-n', '/mnt/c/' + ROOT.as_posix()[3:] + '/board/boot/S99board'],
        [sys.executable, 'experiments/p31_test_rf_overlay.py'],
    ]
    report = dict(status='running', checks=[], hardware_access=False)
    for index, command in enumerate(commands):
        proc = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=120)
        (out / f'check{index}.stdout').write_bytes(proc.stdout)
        (out / f'check{index}.stderr').write_bytes(proc.stderr)
        passed = proc.returncode == (2 if index == 2 else 0)
        report['checks'].append(dict(command=command, exit_code=proc.returncode, passed=passed))
    script = ROOT / 'board/boot/S99board'
    report['script_sha256'] = hashlib.sha256(script.read_bytes()).hexdigest()
    report['script_bytes'] = script.stat().st_size
    report['status'] = 'focused_checks_passed' if all(c['passed'] for c in report['checks']) else 'failed'
    (out / 'report.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(out)
    print(report['status'])
    return 0 if report['status'] == 'focused_checks_passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
