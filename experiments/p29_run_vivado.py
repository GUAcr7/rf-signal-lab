"""Run one staged vendor migration task and retain its true exit/evidence."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['package', 'rf', 'display', 'display-upgrade', 'rf-synth', 'display-synth', 'audit', 'display-clock'])
    args = parser.parse_args()
    active = json.loads((ROOT / 'results/p29-active-build.json').read_text('utf-8'))
    work = Path(active['work'])
    names = {'package': ('package_ips.tcl', 'P29_ALL_IPS_PACKAGED'),
             'rf': ('create_rf.tcl', 'P29_RF_BD_VALIDATED'),
             'display': ('inspect_display.tcl', 'P29_DISPLAY_PROJECT_OPENED'),
             'display-upgrade': ('upgrade_display.tcl', 'P29_DISPLAY_BD_VALIDATED'),
             'rf-synth': ('synth_rf.tcl', 'P29_RF_SYNTH_PASS'),
             'display-synth': ('synth_display.tcl', 'P29_DISPLAY_SYNTH_PASS'),
             'audit': ('audit_designs.tcl', 'P29_COMPILED_REPORTS_WRITTEN'),
             'display-clock': ('refine_display_clock.tcl', 'P29_DISPLAY_CLOCK_MODEL_VERIFIED')}
    script, marker = names[args.stage]
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out = ROOT / 'results' / f'p29-{args.stage}-{stamp}'
    out.mkdir(exist_ok=False)
    record = dict(created_utc=datetime.now(timezone.utc).isoformat(), stage=args.stage,
                  work=str(work), preparation=active['preparation'], status='running',
                  board_operations=False, vendor_originals_modified=False,
                  script_sha256=hashlib.sha256((work / script).read_bytes()).hexdigest())
    def save():
        (out / 'report.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8', newline='\n')
    save()
    shutil.copy2(work / script, out / script)
    tool = 'E:/FPGA_Tools/Xilinx/Vivado/2021.1/bin/vivado.bat'
    command = [tool, '-mode', 'batch', '-notrace', '-source', str(work / script),
               '-log', str(out / 'vivado.log'), '-journal', str(out / 'vivado.jou')]
    try:
        with (out / 'stdout.txt').open('wb') as stdout, (out / 'stderr.txt').open('wb') as stderr:
            result = subprocess.run(command, cwd=work, stdout=stdout, stderr=stderr, timeout=1200)
        record['exit_code'] = result.returncode
        text = (out / 'stdout.txt').read_text('utf-8', errors='replace')
        record['errors'] = [line for line in text.splitlines() if 'ERROR:' in line or '_FAILED' in line][-15:]
        record['status'] = 'passed' if result.returncode == 0 and marker in text and not record['errors'] else 'failed'
        record['markers'] = [line for line in text.splitlines() if line.startswith('P29_')]
        if args.stage == 'package':
            preparation = json.loads(Path(active['preparation']).read_text('utf-8'))
            record['components'] = []
            for name in preparation['custom_ips_dependency_order']:
                path = work / 'adi/library' / name / 'component.xml'
                if path.exists():
                    record['components'].append(dict(ip=name, path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        for name in ('rf-ip-status.rpt', 'rf-migrated-bd.tcl', 'display-ip-status.rpt',
                     'display-upgraded-ip-status.rpt', 'display-config-before.txt',
                     'display-config-after.txt', 'display-config-delta.txt', 'display-migrated-bd.tcl',
                     'rf-synth-utilization.rpt', 'rf-synth-timing.rpt', 'rf-synth-check-timing.rpt',
                     'display-synth-utilization.rpt', 'display-synth-timing.rpt', 'display-synth-check-timing.rpt'):
            path = work / name
            if path.exists():
                shutil.copy2(path, out / name)
        if args.stage == 'audit':
            for path in work.glob('*-compiled-*.rpt'):
                shutil.copy2(path, out / path.name)
        if args.stage == 'display-clock':
            for path in work.glob('display-clock-*.rpt'):
                shutil.copy2(path, out / path.name)
    except Exception as error:
        record.update(status='failed', error=str(error))
        raise
    finally:
        record['ended_utc'] = datetime.now(timezone.utc).isoformat()
        save()
        print(out, flush=True)
    print(record['status'], record.get('exit_code'), flush=True)
    for message in record.get('errors', []):
        print(message)
    return 0 if record['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
