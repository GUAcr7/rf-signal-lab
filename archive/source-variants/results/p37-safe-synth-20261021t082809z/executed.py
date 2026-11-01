"""Synthesize/route only the independently generated, pinned safe-clock copy."""
import argparse
from datetime import datetime, timezone
import hashlib, json, os, re, subprocess
from pathlib import Path
from p32_session import ROOT
from p35_build_ttl import make_tcl, GUARDS

MMCM_GUARD=r'''
set m [get_cells -quiet -hier -filter {REF_NAME == MMCME2_ADV && NAME =~ *clk_wiz_0*}]
if {[llength $m]!=1} {error "safe MMCM instance ambiguous"}
foreach {key wanted} {CLKFBOUT_MULT_F 16.5 DIVCLK_DIVIDE 2 CLKOUT0_DIVIDE_F 25} {
 set actual [get_property $key $m]
 if {abs($actual-$wanted)>0.0001} {error "unsafe MMCM $key $actual"}
 puts "P37_MMCM $key=$actual"
}
puts "P37_SAFE_MMCM_PRIMITIVE_PASS"
'''
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',choices=['synth','route'])
    parser.add_argument('--prepare-report',type=Path,required=True)
    args=parser.parse_args()
    prep=json.loads(args.prepare_report.read_text('utf-8'));work=Path(prep['work'])
    if prep['status']!='passed_safe_clock_BD_and_generated_primitive_not_routed' or not prep['source_unchanged']:raise RuntimeError('unaccepted generated copy')
    if not re.fullmatch(r'E:[/\\]p37-clock-\d{6}',str(work)):raise RuntimeError('unexpected work directory')
    bd=Path(prep['candidate_BD'])
    if sha(bd)!=prep['candidate_BD_sha256']:raise RuntimeError('candidate BD changed')
    for item in prep['generated_primitive']:
        if sha(Path(item['path']))!=item['sha256']:raise RuntimeError('generated MMCM changed')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p37-safe-'+args.stage+'-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    report=dict(schema='rfsig.p37_safe_clock_build.v1',status='preparing',stage=args.stage,work=str(work),
        prepare_report=str(args.prepare_report.resolve()),prepare_report_sha256=sha(args.prepare_report),
        candidate_BD=str(bd),candidate_BD_sha256=sha(bd),board_operations=False,
        external_IO_timing_closed=False,CDC_closed=False,production_release=False,
        original_hashes_before={p:sha(Path(p)) for p in prep['source_hashes_before']})
    def save():(out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    save()
    try:
        tcl=make_tcl(work,out,args.stage).replace(GUARDS,GUARDS+MMCM_GUARD)
        tcl=tcl.replace('p35-ttl-'+args.stage+'.dcp','p37-safe-'+args.stage+'.dcp').replace('P35_','P37_')
        script=out/'executed.tcl';script.write_text(tcl,encoding='utf-8',newline='\n')
        (out/'executed.py').write_bytes(Path(__file__).read_bytes());(out/'prepare-report.json').write_bytes(args.prepare_report.read_bytes())
        command=['E:/FPGA_Tools/Xilinx/Vivado/2021.1/bin/vivado.bat','-mode','batch','-notrace','-source',str(script),'-log',str(out/'vivado.log'),'-journal',str(out/'vivado.jou')]
        env=os.environ.copy();env['XILINXD_LICENSE_FILE']='E:/FPGA_Tools/Downloads/Xilinx.lic'
        report.update(status='running',command=command);save()
        with (out/'stdout.txt').open('wb') as log:
            proc=subprocess.Popen(command,cwd=work,env=env,stdout=log,stderr=subprocess.STDOUT)
            report['child_pid']=proc.pid;save()
            try:code=proc.wait(timeout=1800)
            except subprocess.TimeoutExpired:
                subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],capture_output=True);proc.wait(timeout=30);raise
        text=(out/'stdout.txt').read_text('utf-8',errors='replace');report['exit_code']=code
        report['errors']=[line for line in text.splitlines() if line.startswith('ERROR:')]
        report['markers']=[line for line in text.splitlines() if line.startswith('P37_')]
        if code or report['errors'] or 'P37_SAFE_MMCM_PRIMITIVE_PASS' not in text or 'P37_TTL_'+args.stage.upper()+'_PASS' not in text:raise RuntimeError('native stage or clock guard failed')
        report['status']='passed_native_'+args.stage+'_within_declared_constraints_only'
        checkpoint=work/('p37-safe-'+args.stage+'.dcp');report.update(checkpoint=str(checkpoint),checkpoint_sha256=sha(checkpoint))
        report['report_hashes']={p.name:sha(p) for p in out.glob('*.rpt')}
        report['timing_claim']='All user specified timing constraints are met.' in (out/'timing.rpt').read_text('utf-8',errors='replace')
        cdc=(out/'cdc.rpt').read_text('utf-8',errors='replace')
        rows=[dict(rule=m[1],severity=m[2],count=int(m[3])) for m in re.finditer(r'^(CDC-\d+)\s+(Critical|Warning|Info)\s+(\d+)\s+',cdc,re.M)]
        if not rows:raise RuntimeError('missing CDC summary; cannot assume zero')
        report['CDC_summary']=rows;report['CDC_critical_count']=sum(r['count'] for r in rows if r['severity']=='Critical')
        if sha(bd)!=report['candidate_BD_sha256']:raise RuntimeError('BD changed during build')
    except Exception as exc:report.update(status='failed',error=repr(exc))
    finally:
        report['original_hashes_after']={p:sha(Path(p)) for p in prep['source_hashes_before']}
        report['originals_unchanged']=report['original_hashes_before']==report['original_hashes_after']
        if not report['originals_unchanged']:report['status']='failed_original_changed'
        report['ended_utc']=datetime.now(timezone.utc).isoformat();save();print(out,flush=True);print(report['status'],flush=True)
    return 0 if report['status'].startswith('passed_') else 1
if __name__=='__main__':raise SystemExit(main())
