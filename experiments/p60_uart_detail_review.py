"""Read the frozen P201 routed checkpoint; emit detailed CDC evidence only.

No reimplementation, constraints changes, bitstream generation or board access.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    source = ROOT / 'results/p201-uart-route-20261024T024517Z/report.json'
    parent = json.loads(source.read_text('utf-8'))
    checkpoint = source.parent / 'uart-routed.dcp'
    if parent['board_operations'] or sha(checkpoint) != parent['files_sha256']['uart-routed.dcp']:
        raise ValueError('Frozen offline checkpoint changed')
    out = ROOT / 'results' / datetime.now(timezone.utc).strftime('p60-uart-detail-%Y%m%dT%H%M%SZ')
    out.mkdir()
    record = dict(status='collecting_offline_evidence', board_operations=False,
        deployable=False, bitstream_generated=False, constraints_changed=False,
        parent=str(source), parent_sha256=sha(source), checkpoint_sha256=sha(checkpoint))
    def save():
        (out / 'report.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    script = out / 'read-checkpoint.tcl'
    script.write_text('set_param general.maxThreads 2\nopen_checkpoint {' + checkpoint.as_posix() + '}\n'
        'report_cdc -details -file {' + (out / 'cdc-details.rpt').as_posix() + '}\n'
        'check_timing -verbose -file {' + (out / 'check-timing.rpt').as_posix() + '}\n'
        'report_clocks -file {' + (out / 'clocks.rpt').as_posix() + '}\n'
        'set f [open {' + (out / 'UART-properties.txt').as_posix() + '} w]\n'
        'foreach p {ext_uart_tx ext_uart_rx} {\n'
        '  puts $f "$p pin=[get_property PACKAGE_PIN [get_ports $p]] io=[get_property IOSTANDARD [get_ports $p]]"\n'
        '}\nclose $f\nputs "P60_READ_ONLY_CHECKPOINT_REPORTS_DONE"\nclose_design\n', encoding='ascii')
    record['script_sha256'] = sha(script)
    save(); print(out, flush=True)
    env = os.environ.copy()
    for name in list(env):
        if name.startswith('ADI_') or name == 'REQUIRED_VIVADO_VERSION':
            env.pop(name)
    try:
        with (out / 'tool-stdout.txt').open('wb') as log:
            result = subprocess.run(['E:/FPGA_Tools/Xilinx/Vivado/2021.1/bin/vivado.bat',
                '-mode', 'batch', '-notrace', '-source', str(script),
                '-log', str(out / 'vivado.log'), '-journal', str(out / 'vivado.jou')],
                cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=240)
        record['exit_code'] = result.returncode
        if result.returncode or 'P60_READ_ONLY_CHECKPOINT_REPORTS_DONE' not in (out / 'tool-stdout.txt').read_text(errors='replace'):
            raise ValueError('Checkpoint evidence extraction did not finish')
        text = (out / 'cdc-details.rpt').read_text(errors='replace')
        record['CDC_rule_occurrences'] = {rule: len(re.findall(r'\b' + rule + r'\b', text))
                                         for rule in sorted(set(re.findall(r'CDC-\d+', text)))}
        record['frozen_checkpoint_unchanged'] = sha(checkpoint) == record['checkpoint_sha256']
        if not record['frozen_checkpoint_unchanged']:
            raise ValueError('Checkpoint changed during read')
        record['files_sha256'] = {name: sha(out / name) for name in
            ('read-checkpoint.tcl', 'cdc-details.rpt', 'check-timing.rpt', 'clocks.rpt', 'UART-properties.txt', 'tool-stdout.txt')}
        record['status'] = 'collected_detailed_UART_candidate_CDC_pending_endpoint_review'
    except Exception as error:
        record.update(status='failed_or_incomplete_offline_detail_read', error=repr(error))
    save(); print(record['status'], flush=True)
    return 0 if record['status'].startswith('collected_') else 1


if __name__ == '__main__':
    raise SystemExit(main())
