"""Full offline synthesis/routing for candidate UART; no bitstream or board access."""
import argparse,hashlib,json,shutil,subprocess
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--validation',type=Path,required=True);args=p.parse_args()
    previous=json.loads(args.validation.read_text());work=Path(previous['work']).resolve()
    if work.parent!=Path('E:/FPGA_Tools/Work').resolve() or not work.name.startswith('uart-') or previous['board_operations']:raise ValueError('isolated work required')
    project=work/'hdl/projects/pzp201';out=ROOT/'results'/datetime.now(timezone.utc).strftime('p201-uart-route-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    r=dict(status='running_full_offline_build',board_operations=False,deployable=False,bitstream_generated=False,
        validation=str(args.validation.resolve()),validation_sha256=sha(args.validation),work=str(work))
    def save():(out/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    save()
    prefix='''open_project pzp201.xpr
open_bd_design [get_files */system.bd]
validate_bd_design
set ps [get_bd_cells sys_ps7]
if {[get_property CONFIG.PCW_UART0_PERIPHERAL_ENABLE $ps] != 1} {error "UART0 disabled"}
if {[get_property CONFIG.PCW_UART0_UART0_IO $ps] ne "EMIO"} {error "UART0 not EMIO"}
if {[get_property CONFIG.PCW_UART1_UART1_IO $ps] ne "MIO 12 .. 13"} {error "console moved"}
foreach {port pin direction} {ext_uart_tx UART0_TX O ext_uart_rx UART0_RX I} {
  set net [get_bd_nets -of_objects [get_bd_ports $port]]
  set expected [get_bd_nets -of_objects [get_bd_pins sys_ps7/$pin]]
  if {[get_property DIR [get_bd_ports $port]] ne $direction || [llength $net] != 1 || $net ne $expected} {error "UART route/direction"}
}
write_bd_tcl -force uart-generated-bd.tcl
report_ip_status -file uart-ip-status.rpt
puts "UART_BD_ROUTE_AND_CONSOLE_CHECKS_PASS"
'''
    script=out/'route.tcl';script.write_text(prefix+'''
set_param general.maxThreads 2
generate_target all [get_files */system.bd]
launch_runs synth_1 -jobs 2
wait_on_run synth_1
if {[get_property PROGRESS [get_runs synth_1]] ne "100%"} {error "synthesis incomplete"}
puts "UART_FULL_SYNTHESIS_PASS"
launch_runs impl_1 -to_step route_design -jobs 2
wait_on_run impl_1
if {[get_property PROGRESS [get_runs impl_1]] ne "100%"} {error "implementation incomplete"}
open_run impl_1
foreach {port pin} {ext_uart_tx E17 ext_uart_rx E18} {
  if {[get_property PACKAGE_PIN [get_ports $port]] ne $pin} {error "wrong UART pad"}
  if {[get_property IOSTANDARD [get_ports $port]] ne "LVCMOS33"} {error "wrong UART voltage constraint"}
}
report_io -file uart-io.rpt
report_timing_summary -report_unconstrained -file uart-timing.rpt
report_cdc -file uart-cdc.rpt
report_drc -file uart-drc.rpt
check_timing -verbose -file uart-check-timing.rpt
report_utilization -file uart-utilization.rpt
write_checkpoint -force uart-routed.dcp
set f [open uart-run-stats.txt w]
foreach property {STATS.WNS STATS.WHS STATS.TNS STATS.THS STATUS} {
    puts $f "$property=[get_property $property [get_runs impl_1]]"
}
close $f
puts "UART_FULL_ROUTING_AND_3V3_PADS_COMPLETE_NOT_RELEASE"
close_project
''',encoding='utf-8')
    shutil.copy2(script,project/'uart_route.tcl')
    try:
        with (out/'vivado.log').open('wb') as f:
            completed=subprocess.run(['E:/FPGA_Tools/Xilinx/Vivado/2021.1/bin/vivado.bat','-mode','batch','-notrace','-source','uart_route.tcl'],cwd=project,stdout=f,stderr=subprocess.STDOUT,timeout=1800)
        text=(out/'vivado.log').read_text(errors='replace');r['exit_code']=completed.returncode
        if completed.returncode or 'UART_FULL_ROUTING_AND_3V3_PADS_COMPLETE_NOT_RELEASE' not in text:raise ValueError('full build failed or incomplete')
        for name in ('uart-generated-bd.tcl','uart-ip-status.rpt','uart-io.rpt','uart-timing.rpt','uart-cdc.rpt','uart-drc.rpt','uart-check-timing.rpt','uart-utilization.rpt','uart-routed.dcp','uart-run-stats.txt'):
            shutil.copy2(project/name,out/name)
        ip=project/'pzp201.gen/sources_1/bd/system/ip/system_sys_ps7_0'
        for name in ('ps7_init.c','ps7_init.h','ps7_init.tcl','ps7_parameters.xml'):shutil.copy2(ip/name,out/name)
        stats=dict(line.split('=',1) for line in (out/'uart-run-stats.txt').read_text().splitlines())
        r.update(status='completed_full_offline_routing_requires_timing_and_board_acceptance',run_stats=stats,
            route_complete=True,full_timing_accepted=False,new_boot_image_built=False,
            note='Generated PS init must be incorporated into a reviewed boot flow with matching PL/DTB; no hot-load or deployment performed.')
    except Exception as e:r.update(status='failed_or_incomplete_offline_build',error=repr(e))
    # Retain per-IP/main failure logs even when a run aborts before final reports.
    for run in (project/'pzp201.runs').glob('*'):
        for name in ('runme.log','runme.vds'):
            f=run/name
            if f.is_file():
                dest=out/'runs'/run.name/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(f,dest)
    r['files_sha256']={p.relative_to(out).as_posix():sha(p) for p in out.rglob('*') if p.is_file() and p.name!='report.json'};save()
    print(out/'report.json',flush=True);print(r['status'],flush=True)
    return 0 if r['status'].startswith('completed_') else 1
if __name__=='__main__':raise SystemExit(main())
