"""Summarize native TTL reports without editing stage evidence or hiding open checks."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('result',type=Path)
    args=parser.parse_args()
    out=args.result.resolve()
    original=out/'report.json'
    stage=json.loads(original.read_text('utf-8'))
    summary=dict(status='summarizing_native_evidence',stage=stage['stage'],
        stage_report_sha256=sha(original),summary_script_sha256=sha(Path(__file__)),
        native_exit_code=stage.get('exit_code'),native_markers=stage.get('markers',[]),
        board_operations=False,bitstream_generated=False,external_timing_closed=False,
        source_DMA_patch_applied=False,notes=[
            'Synthesis timing precedes placement/route and is not final timing signoff',
            'External-delay omissions and CDC Critical entries remain release limitations',
            'Native report counts are independent of the first builder pipe-table parser'])
    hashes=stage.get('report_hashes',{})
    for name,expected in hashes.items():
        if sha(out/name)!=expected:raise RuntimeError('native evidence changed '+name)
    timing=(out/'timing.rpt').read_text('utf-8',errors='replace')
    lines=timing.splitlines()
    for index,line in enumerate(lines):
        if line.lstrip().startswith('WNS(ns)'):
            row=lines[index+2].split()
            if len(row)!=12:raise RuntimeError('native timing summary shape changed')
            summary['native_design_timing']={
                'WNS_ns':float(row[0]),'TNS_ns':float(row[1]),'setup_failing_endpoints':int(row[2]),
                'WHS_ns':float(row[4]),'THS_ns':float(row[5]),'hold_failing_endpoints':int(row[6]),
                'WPWS_ns':float(row[8]),'TPWS_ns':float(row[9]),'pulse_width_failing_endpoints':int(row[10])}
            break
    if 'native_design_timing' not in summary:raise RuntimeError('missing native global timing summary')
    summary['all_declared_user_timing_met']='All user specified timing constraints are met.' in timing
    cdc=(out/'cdc.rpt').read_text('utf-8',errors='replace')
    rows=[dict(rule=m[1],severity=m[2],count=int(m[3]),description=m[4])
        for m in re.finditer(r'^(CDC-\d+)\s+(Critical|Warning|Info)\s+(\d+)\s+(.+)$',cdc,re.M)]
    if not rows:raise RuntimeError('native CDC summary missing')
    summary['CDC_summary']=rows
    summary['CDC_critical_count']=sum(row['count'] for row in rows if row['severity']=='Critical')
    check=(out/'check-timing.rpt').read_text('utf-8',errors='replace')
    summary['check_timing_counts']={m[1]:int(m[2])
        for m in re.finditer(r'^\d+\. checking (\w+) \((\d+)\)',check,re.M)}
    summary['originals_unchanged']=stage['originals_unchanged']
    summary['native_report_hashes_verified']=len(hashes)
    summary['status']='native_evidence_summarized_with_open_checks_retained'
    summary['created_utc']=datetime.now(timezone.utc).isoformat()
    destination=out/'post-summary.json'
    if destination.exists():raise RuntimeError('do not silently replace prior summary')
    destination.write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    print(destination)
    print(json.dumps({k:summary[k] for k in ['stage','native_design_timing','all_declared_user_timing_met','CDC_critical_count','check_timing_counts']},indent=2))

if __name__=='__main__':main()
