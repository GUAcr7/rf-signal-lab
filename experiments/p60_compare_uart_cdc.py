"""Compare actual CDC endpoints with the historical P201 baseline, read-only."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path):
    result = []
    for line in path.read_text(errors='replace').splitlines():
        match = re.match(r'^\s*(\d+)\s+(CDC-\d+)\s+(Critical|Info|Warning)\b', line)
        if match:
            fields = line.split()
            source, destination = fields[-2:]
            if '/' not in source or '/' not in destination:
                raise ValueError('Missing endpoint names')
            result.append(dict(rule=match[2], severity=match[3], source=source,
                               destination=destination, original_line=line))
    if not result:
        raise ValueError('No detailed endpoint rows')
    return result


def key(row):
    return row['rule'], row['source'], row['destination']


def main():
    detail = ROOT / 'results/p60-uart-detail-20261025T025319Z/report.json'
    record = json.loads(detail.read_text('utf-8'))
    current = detail.parent / 'cdc-details.rpt'
    if sha(current) != record['files_sha256']['cdc-details.rpt']:
        raise ValueError('Current detailed report changed')
    baseline = ROOT / 'results/p06-cdc-audit-20261015-200505/reports/cdc.rpt'
    new, old = rows(current), rows(baseline)
    critical_new = [r for r in new if r['severity'] == 'Critical']
    critical_old = [r for r in old if r['severity'] == 'Critical']
    a, b = Counter(map(key, critical_new)), Counter(map(key, critical_old))
    groups = Counter(r['destination'].split('/')[2] for r in critical_new)
    out = ROOT / 'results' / datetime.now(timezone.utc).strftime('p60-uart-comparison-%Y%m%dT%H%M%SZ')
    out.mkdir()
    source = ROOT / 'fpga/vendor-baseline/source/plutosdr-fw/hdl/library/axi_dmac/request_arb.v'
    result = dict(status='reviewed_UART_candidate_CDC_endpoint_comparison_not_release',
        board_operations=False, deployable=False, bitstream_generated=False,
        detail_report=detail.relative_to(ROOT).as_posix(), detail_report_sha256=sha(detail),
        current_CDC=current.relative_to(ROOT).as_posix(), current_CDC_sha256=sha(current),
        historical_CDC=baseline.relative_to(ROOT).as_posix(), historical_CDC_sha256=sha(baseline),
        current_rule_counts=dict(Counter(r['rule'] for r in new)),
        baseline_rule_counts=dict(Counter(r['rule'] for r in old)),
        current_critical=len(critical_new), baseline_critical=len(critical_old),
        critical_endpoint_multisets_identical=a == b,
        added_critical_endpoints=[list(k) + [v] for k, v in (a - b).items()],
        removed_critical_endpoints=[list(k) + [v] for k, v in (b - a).items()],
        current_critical_destination_groups=dict(groups),
        UART_named_critical_rows=[r for r in critical_new if re.search('uart', r['source'] + r['destination'], re.I)],
        current_critical_rows=critical_new,
        request_arb_source=source.relative_to(ROOT).as_posix(), request_arb_sha256=sha(source),
        interpretation=[
            'Equal endpoint sets localize inherited structural warnings; they do not prove CDC safe.',
            'Clock definitions, timing exceptions and placement are not compared by this endpoint test.',
            'EOT metadata RAM in request_arb spans req/src/dest clocks; review ID lifetime and handshake before acceptance.',
            'External RF delays, UART initialization, recoverable image and physical loopback remain separate release gates.',
            'No blanket false-path exception or ASYNC_REG patch was applied.'
        ])
    (out / 'report.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(out)
    print(json.dumps({k: result[k] for k in ('current_critical', 'baseline_critical',
        'critical_endpoint_multisets_identical', 'current_critical_destination_groups',
        'added_critical_endpoints', 'UART_named_critical_rows')}, indent=2))


if __name__ == '__main__':
    main()
