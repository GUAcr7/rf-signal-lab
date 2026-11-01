"""Inventory the final P30 routed CDC report, keeping all findings unwaived."""
from collections import Counter,defaultdict
from datetime import datetime,timezone
import hashlib
import json
import re
from p32_session import ROOT
from pathlib import Path


def main():
    source=Path('E:/p30c-1019-174235/merged-route-cdc.rpt')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p32-final-cdc-%Y%m%dT%H%M%SZ')
    out.mkdir(exist_ok=False)
    source_clock=dest_clock=None;rows=[]
    for line in source.read_text('utf-8').splitlines():
        if line.startswith('Source Clock:'):source_clock=line.split(':',1)[1].strip()
        if line.startswith('Destination Clock:'):dest_clock=line.split(':',1)[1].strip()
        if re.match(r'^\s*\d+\s+CDC-\d+\s+Critical\s',line):
            parts=re.split(r'\s{2,}',line.strip())
            rows.append(dict(row=int(parts[0]),rule=parts[1],description=parts[3],
                depth=parts[4],exception=parts[5],source=parts[-2],destination=parts[-1],
                source_clock=source_clock,destination_clock=dest_clock))
    if Counter(r['rule'] for r in rows)!=Counter({'CDC-1':50,'CDC-10':4,'CDC-12':2,'CDC-13':2}):
        raise RuntimeError('final routed report changed; review before reusing dispositions')
    groups=defaultdict(list)
    for row in rows:
        src,dst=row['source'],row['destination']
        if row['rule']=='CDC-13':key='divider_clock_mux_select'
        elif 'eot_mem' in src:key='EOT_metadata_lifetime_and_handshake'
        elif 'i_sync_control' in dst and row['rule']=='CDC-10':key='combinational_sync_id_decode'
        elif 'i_sync_status' in dst:key='reconvergent_enable_and_empty_status'
        elif 'cdc_sync_fifo_ram_reg' in src:key='FIFO_bundled_payload_handshake'
        else:key='other_individual_review'
        groups[key].append(row)
    instructions={
        'EOT_metadata_lifetime_and_handshake':'Prove request-slot EOT writes precede cross-domain use and cannot be overwritten before all consumers finish. Exercise actual FIFO/MM endpoints, ID wrap, stalls, abort and re-enable. Then review physical bundled-data max delay; do not simply insert per-bit synchronizers.',
        'combinational_sync_id_decode':'Inspect request/response ID comparison and enabled feedback for glitches before synchronizers. Verify abort/resync in actual endpoints before proposing registered handshake changes; any RTL change requires reroute.',
        'reconvergent_enable_and_empty_status':'Trace enabled OR not-empty domain ownership, synchronization and reconvergence; prove stop/drain never acknowledges before outstanding data completes.',
        'FIFO_bundled_payload_handshake':'Verify FIFO data hold time versus synchronized pointer visibility, end-of-transfer payload sampling and reset/abort behavior. Existing ASYNC AXIS/AXIS test alone does not cover actual FIFO/MM endpoints.',
        'divider_clock_mux_select':'Review BUFGMUX_CTRL select semantics and permitted dynamic clock switching. Confirm software changes rate only with channels quiescent and domain reset policy; digital FIFO sims do not establish safe clock switching.',
        'other_individual_review':'Read exact path and RTL before disposition.'}
    report=dict(status='final_routed_findings_classified_not_waived',source=str(source),
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),total_critical=len(rows),
        unique_source_destination_pairs=len({(r['source'],r['destination']) for r in rows}),
        counts_by_rule=dict(Counter(r['rule'] for r in rows)),
        groups={k:dict(count=len(v),rows=v,next_verification=instructions[k],disposition='open') for k,v in groups.items()},
        prior_inventory_scope='p30_cdc_inventory.py reads historical P29 RF-only 59-finding report; it is not this final merged 58-finding report',
        RTL_changed=False,constraints_changed=False,waivers_added=False,
        functional_simulation_added=False,all_CDC_resolved=False)
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    (out/'merged-route-cdc.rpt').write_bytes(source.read_bytes())
    print(out);print(json.dumps({k:v['count'] for k,v in report['groups'].items()}));print('unique pairs',report['unique_source_destination_pairs'])


if __name__=='__main__':main()
