"""Offline TTL33 generation/synthesis/route with pinned inputs and native reports.

No bitstream, board, firmware, clock waiver, or original project operation.
The only writable Vivado project is the independently reviewed P33 TTL copy.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]
BIN=Path('E:/FPGA_Tools/Xilinx/Vivado/2021.1/bin')
DEFAULT=Path('E:/p33-ttl-114312')
BD=Path('project/combined.srcs/sources_1/bd/system/system.bd')

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

GUARDS=r'''
set blackboxes [get_cells -quiet -hier -filter {IS_BLACKBOX == 1}]
if {[llength $blackboxes]} {error "unresolved cells $blackboxes"}
set auxiliary [get_cells -quiet -hier -filter {NAME =~ *lvds_n_x_7to1* || NAME =~ *dual_pixel* || NAME =~ *parity_flag* || REF_NAME =~ PLLE2*}]
if {[llength $auxiliary]} {error "unused LVDS/PLL remains $auxiliary"}
if {[llength [get_ports -quiet lvds_*]] || [llength [get_ports -quiet o_video*]]} {error "unused external port remains"}
proc single_clock {obj expected label} {
  if {[llength $obj]!=1} {error "$label object count [llength $obj]"}
  set clock [get_clocks -quiet -of_objects $obj]
  if {[llength $clock]!=1} {error "$label clock count [llength $clock]: $clock"}
  set period [get_property PERIOD $clock]
  if {abs($period-$expected)>0.002} {error "$label period $period != $expected"}
  puts "P35_CLOCK $label $clock period_ns=$period"
  return $clock
}
set ps [get_cells -hier -filter {REF_NAME == PS7}]
if {[llength $ps]!=1} {error "PS7 count [llength $ps]"}
set fclk0 {}; set fclk1 {}
foreach p [get_pins -of_objects $ps] {
  set rn [get_property REF_PIN_NAME $p]
  if {$rn eq {FCLKCLK[0]}} {set fclk0 $p}
  if {$rn eq {FCLKCLK[1]}} {set fclk1 $p}
}
set ps100 [single_clock $fclk0 10.0 ps_fclk0]
set ps200 [single_clock $fclk1 5.0 ps_fclk1]
set pixel [single_clock [get_ports lcd_pclk] [expr {1000.0/33.0}] lcd_pixel]
if {![get_property IS_GENERATED $pixel]} {error "LCD clock is not generated"}
set clk_input [get_pins -quiet -hier -filter {NAME =~ */clk_wiz_0/*/mmcm_adv_inst/CLKIN1}]
set wiz100 [single_clock $clk_input 10.0 clockwiz_input]
if {$wiz100 ne $ps100} {error "ClockWiz input creates a new clock instead of inherited FCLK0"}
set axi_pin [get_pins -quiet -hier -filter {NAME =~ */clk_wiz_0/s_axi_aclk}]
set wiz200 [single_clock $axi_pin 5.0 clockwiz_axi]
if {$wiz200 ne $ps200} {error "ClockWiz AXI does not inherit FCLK1"}
if {[llength [get_clocks -quiet *clk_wiz_0/inst/clk_in1]]} {error "internal ClockWiz create_clock remains"}
puts "P35_TTL_CLOCK_GUARD_PASS no_auxiliary_lvds single_pixel_33MHz"
'''

def make_tcl(work,out,stage):
    prefix=f'''set_param general.maxThreads 2
cd {{{work.as_posix()}}}
open_project {{{(work/'project/combined.xpr').as_posix()}}}
if {{[get_property PART [current_project]] ne "xc7z100ffg900-2"}} {{error "wrong device"}}
'''
    if stage=='synth':
        body='''generate_target all [get_files *.bd]
update_compile_order -fileset sources_1
if {[get_property PROGRESS [get_runs synth_1]] eq "100%"} {reset_run synth_1}
launch_runs synth_1 -jobs 2
wait_on_run synth_1
set status [get_property STATUS [get_runs synth_1]]
puts "P35_SYNTH_STATUS $status"
if {[get_property PROGRESS [get_runs synth_1]] ne "100%" || ![string match *Complete* $status]} {exit 40}
open_run synth_1
'''
    else:
        body='''if {[get_property PROGRESS [get_runs synth_1]] ne "100%"} {error "synthesis incomplete"}
launch_runs impl_1 -to_step route_design -jobs 2
wait_on_run impl_1
set status [get_property STATUS [get_runs impl_1]]
puts "P35_ROUTE_STATUS $status"
if {![string match *route_design*Complete* $status]} {exit 41}
open_run impl_1
'''
    reports=''
    commands={
        'utilization':'report_utilization',
        'timing':'report_timing_summary -report_unconstrained',
        'check-timing':'check_timing -verbose',
        'drc':'report_drc', 'cdc':'report_cdc -details',
        'clocks':'report_clocks', 'clock-interaction':'report_clock_interaction',
        'bus-skew':'report_bus_skew -warn_on_violation',
        'methodology':'report_methodology','io':'report_io',
    }
    for name,command in commands.items():
        reports+=f'{command} -file {{{(out/(name+".rpt")).as_posix()}}}\n'
    dcp=work/('p35-ttl-'+stage+'.dcp')
    reports+=f'write_checkpoint -force {{{dcp.as_posix()}}}\n'
    if stage=='route':reports+=f'report_route_status -file {{{(out/"route-status.rpt").as_posix()}}}\n'
    reports+='puts "P35_TTL_'+stage.upper()+'_PASS"\nclose_project\nexit 0\n'
    return prefix+body+GUARDS+reports

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',choices=['synth','route'])
    parser.add_argument('--work',type=Path,default=DEFAULT)
    args=parser.parse_args()
    work=args.work.resolve()
    if work!=DEFAULT.resolve():raise RuntimeError('only reviewed dedicated TTL copy is writable')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p35-ttl-'+args.stage+'-%Y%m%dT%H%M%SZ')
    out.mkdir(exist_ok=False)
    original=[Path('E:/p30c-1019-174235/project/combined.xpr'),
        Path('E:/p30c-1019-174235/merged-route.dcp'),
        Path('E:/p32-pwm2-105934/project/combined.xpr'),
        Path('E:/p32-pwm2-105934')/BD]
    report=dict(status='preparing',stage=args.stage,work=str(work),board_operations=False,
        bitstream_generated=False,firmware_modified=False,ADI_CDC_patch_applied=False,
        external_IO_timing_closed=False,original_hashes_before={str(p):sha(p) for p in original},
        limitations=['External RF/panel delay inputs remain incomplete',
            'CDC warnings are retained; no waivers added',
            'Fresh generation/synthesis/route is not board validation'])
    def save():(out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    save()
    try:
        inputs=[]
        for path in [work/'project/combined.xpr',work/BD,*sorted((work/'hdl').rglob('*')),*sorted((work/'constraints').glob('*.xdc'))]:
            if not path.is_file():continue
            if path.name=='half_clock.xdc':
                # On disk for provenance only; removed from the XPR.
                continue
            relative=path.relative_to(work)
            data=path.read_bytes()
            snap=out/'inputs'/relative
            snap.parent.mkdir(parents=True,exist_ok=True)
            snap.write_bytes(data)
            inputs.append(dict(path=str(path),sha256=hashlib.sha256(data).hexdigest(),bytes=len(data)))
        report['inputs']=inputs
        xpr=(work/'project/combined.xpr').read_text('utf-8')
        if 'half_clock.xdc' in xpr:raise RuntimeError('removed branch constraint still active')
        bd=json.loads((work/BD).read_text('utf-8'))['design']
        if float(bd['components']['clk_wiz_0']['parameters']['CLKOUT1_REQUESTED_OUT_FREQ']['value'])!=33:
            raise RuntimeError('33MHz source contract changed')
        if any(name in bd['components'] for name in ['dual_pixel_24bpp_lvds_mapping_0','lvds_n_x_7to1_sdr_tx_0']):
            raise RuntimeError('auxiliary branch present')
        tcl=out/'executed.tcl'
        tcl.write_text(make_tcl(work,out,args.stage),encoding='utf-8',newline='\n')
        (out/'runner.py').write_bytes(Path(__file__).read_bytes())
        command=[str(BIN/'vivado.bat'),'-mode','batch','-notrace','-source',str(tcl),
            '-log',str(out/'vivado.log'),'-journal',str(out/'vivado.jou')]
        env=os.environ.copy()
        env['XILINXD_LICENSE_FILE']='E:/FPGA_Tools/Downloads/Xilinx.lic'
        report.update(status='running',command=command,license_path_configured=True,timeout_s=1800)
        save()
        with (out/'stdout.txt').open('wb') as log:
            proc=subprocess.Popen(command,cwd=work,env=env,stdout=log,stderr=subprocess.STDOUT)
            report['child_pid']=proc.pid;save()
            try:code=proc.wait(timeout=1800)
            except subprocess.TimeoutExpired:
                subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],capture_output=True)
                proc.wait(timeout=30)
                report['timeout']=True
                raise
        report['exit_code']=code
        text=(out/'stdout.txt').read_text('utf-8',errors='replace')
        report['errors']=[line for line in text.splitlines() if line.startswith('ERROR:')]
        report['critical_warnings']=[line for line in text.splitlines() if line.startswith('CRITICAL WARNING:')]
        report['markers']=[line for line in text.splitlines() if line.startswith('P35_')]
        marker='P35_TTL_'+args.stage.upper()+'_PASS'
        if code or report['errors'] or marker not in text:raise RuntimeError('native stage or guard failed')
        report['status']='passed_native_'+args.stage+'_within_declared_constraints_only'
        report['checkpoint']=str(work/('p35-ttl-'+args.stage+'.dcp'))
        report['checkpoint_sha256']=sha(Path(report['checkpoint']))
        report['report_hashes']={p.name:sha(p) for p in out.glob('*.rpt')}
        timing=(out/'timing.rpt').read_text('utf-8',errors='replace')
        report['timing_claim']='All user specified timing constraints are met.' in timing
        cdc=(out/'cdc.rpt').read_text('utf-8',errors='replace')
        report['CDC_summary_lines']=[line for line in cdc.splitlines() if re.match(r'^CDC-\d+\s+(Critical|Warning|Info)\s+\d+\s',line)][:40]
        report['CDC_critical_count']=sum(int(m[1]) for m in re.finditer(r'^CDC-\d+\s+Critical\s+(\d+)\s',cdc,re.M))
    except Exception as exc:report.update(status='failed',error=repr(exc))
    finally:
        runlog=work/'project/combined.runs'/('synth_1' if args.stage=='synth' else 'impl_1')/'runme.log'
        if runlog.exists():shutil.copy2(runlog,out/'runme.log')
        report['original_hashes_after']={str(p):sha(p) for p in original}
        report['originals_unchanged']=report['original_hashes_before']==report['original_hashes_after']
        if not report['originals_unchanged']:report['status']='failed_originals_changed'
        report['ended_utc']=datetime.now(timezone.utc).isoformat()
        save();print(out,flush=True);print(report['status'],flush=True)
    return 0 if report['status'].startswith('passed_') else 1

if __name__=='__main__':raise SystemExit(main())
