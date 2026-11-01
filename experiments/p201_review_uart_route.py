"""Review routed UART candidate without treating internal slack as release approval."""
import argparse,hashlib,json,re
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--route',required=True,type=Path);args=p.parse_args()
    r=json.loads(args.route.read_text());folder=args.route.parent
    if r['status']!='completed_full_offline_routing_requires_timing_and_board_acceptance' or r['board_operations']:raise ValueError('finished offline route required')
    for name,digest in r['files_sha256'].items():
        if sha(folder/name)!=digest:raise ValueError('route evidence changed')
    io=(folder/'uart-io.rpt').read_text();timing=(folder/'uart-check-timing.rpt').read_text();cdc=(folder/'uart-cdc.rpt').read_text()
    for pad,port,direction in [('E17','ext_uart_tx','OUTPUT'),('E18','ext_uart_rx','INPUT')]:
        if not re.search(r'\|\s*'+pad+r'\s*\|\s*'+port+r'\s*\|[^\n]*\|\s*'+direction+r'\s*\|\s*LVCMOS33\s*\|\s*35\s*\|',io):raise ValueError('routed pad differs')
    counts={k:int(re.search(r'checking '+k+r' \((\d+)\)',timing).group(1)) for k in ('no_clock','unconstrained_internal_endpoints','no_input_delay','no_output_delay')}
    rows=[]
    for line in cdc.splitlines():
        fields=line.split()
        if fields and fields[0] in ('Critical','Info','Warning') and len(fields)>=6:
            numbers=list(map(int,fields[-5:]))
            rows.append(dict(severity=fields[0],source_clock=fields[1],destination_clock=fields[2],endpoints=numbers[0],safe=numbers[1],unsafe=numbers[2],unknown=numbers[3],no_ASYNC_REG=numbers[4]))
    if not rows:raise ValueError('CDC summary missing')
    stats=r['run_stats'];wns=float(stats['STATS.WNS']);whs=float(stats['STATS.WHS'])
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p201-uart-review-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    report=dict(status='routed_UART_pad_checks_pass_system_release_not_accepted',route=str(args.route.resolve()),route_sha256=sha(args.route),
        board_operations=False,deployable=False,routed_UART_pads_checked=True,
        setup_WNS_ns=wns,hold_WHS_ns=whs,constrained_paths_slack_nonnegative=wns>=0 and whs>=0,
        timing_coverage=counts,CDC=rows,CDC_unsafe=sum(v['unsafe'] for v in rows),CDC_unknown=sum(v['unknown'] for v in rows),
        physical_UART_tested=False,observations=['External RF interface delays incomplete; UART pin assignment check is not whole-system timing signoff',
            'CDC report contains rx_clk/fpga clock crossings; no root-cause closure or added false-path exceptions performed',
            'Original vendor files and board runtime untouched'])
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(out/'report.json');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
