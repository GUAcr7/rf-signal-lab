"""Group actual CDC findings for review; this tool never waives a finding."""
from collections import Counter,defaultdict
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]


def main():
    source=ROOT/'results/p29-audit-20261019T091015Z/rf-compiled-cdc.rpt'
    out=ROOT/'results'/('p30-cdc-inventory-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    out.mkdir(exist_ok=False)
    source_clock=dest_clock=None
    rows=[]
    for line in source.read_text('utf-8').splitlines():
        if line.startswith('Source Clock:'):source_clock=line.split(':',1)[1].strip()
        if line.startswith('Destination Clock:'):dest_clock=line.split(':',1)[1].strip()
        if re.match(r'^\s*\d+\s+CDC-\d+\s+Critical\s',line):
            parts=re.split(r'\s{2,}',line.strip())
            rows.append(dict(row=int(parts[0]),rule=parts[1],description=parts[3],depth=parts[4],exception=parts[5],
                source=parts[-2],destination=parts[-1],source_clock=source_clock,destination_clock=dest_clock))
    assert len(rows)==59,len(rows)
    groups=defaultdict(list)
    for row in rows:
        dest=row['destination']
        if 'axi_ad9361_adc_dma/' in dest or 'axi_ad9361_dac_dma/' in dest:
            key='ADI_DMA_request_arbitration_and_FIFO'
        elif 'i_div_clk_gbuf/' in dest or 'i_div_clk' in dest:
            key='ADI_clock_divider_mux'
        elif 'axi_ad9361/' in dest:
            key='ADI_AD9361_control_or_data'
        else:key='other_requires_individual_review'
        groups[key].append(row)
    report=dict(status='classified_not_waived',created_utc=datetime.now(timezone.utc).isoformat(),
        source=str(source),sha256=hashlib.sha256(source.read_bytes()).hexdigest(),total_critical=len(rows),
        counts_by_rule=dict(Counter(row['rule'] for row in rows)),
        groups={key:dict(count=len(values),rules=dict(Counter(row['rule'] for row in values)),rows=values,
            disposition='pending code/handshake/clock-select review; no exception added') for key,values in groups.items()},
        note='Same endpoint may occur under alternate divider clocks. Counts are tool findings, not independent demonstrated hardware faults.',
        constraints_changed=False)
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(out)
    print(json.dumps({key:value['count'] for key,value in report['groups'].items()},indent=2))
    for key,values in groups.items():
        print(key)
        for row in values[:4]:print(row['rule'],row['destination'])


if __name__=='__main__':main()
