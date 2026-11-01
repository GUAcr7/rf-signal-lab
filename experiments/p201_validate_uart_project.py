"""Resume only an isolated UART candidate after recording its first failed query."""
import argparse,hashlib,json,shutil,subprocess
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser();p.add_argument('--candidate',required=True,type=Path);args=p.parse_args()
    candidate=json.loads(args.candidate.read_text());work=Path(candidate['work']).resolve()
    if work.parent!=Path('E:/FPGA_Tools/Work').resolve() or not work.name.startswith('uart-') or candidate['board_operations']:
        raise ValueError('isolated offline UART work required')
    project=work/'hdl/projects/pzp201';out=ROOT/'results'/datetime.now(timezone.utc).strftime('p201-uart-validated-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    r=dict(status='checking',board_operations=False,deployable=False,bitstream_generated=False,
        candidate=str(args.candidate.resolve()),candidate_sha256=sha(args.candidate),work=str(work))
    def save():(out/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    save()
    original=project/'uart_validate.tcl'
    shutil.copy2(original,out/'previous-uart-validate.tcl')
    script=out/'resume.tcl'
    script.write_text('''open_project pzp201.xpr
open_bd_design [get_files */system.bd]
validate_bd_design
set ps [get_bd_cells sys_ps7]
if {[get_property CONFIG.PCW_UART0_PERIPHERAL_ENABLE $ps] != 1} {error "UART0 disabled"}
if {[get_property CONFIG.PCW_UART0_UART0_IO $ps] ne "EMIO"} {error "UART0 not EMIO"}
if {[get_property CONFIG.PCW_UART1_UART1_IO $ps] ne "MIO 12 .. 13"} {error "console moved"}
foreach {port pin direction} {ext_uart_tx UART0_TX O ext_uart_rx UART0_RX I} {
  set net [get_bd_nets -of_objects [get_bd_ports $port]]
  set expected [get_bd_nets -of_objects [get_bd_pins sys_ps7/$pin]]
  puts "UART_ROUTE port=$port actual=$net expected=$expected"
  puts "UART_PIN_OLD_QUERY [get_bd_pins -of_objects $net -filter \\"NAME == sys_ps7/$pin\\"]"
  if {[get_property DIR [get_bd_ports $port]] ne $direction} {error "UART direction"}
  if {[llength $net] != 1 || $net ne $expected} {error "UART disconnected"}
}
write_bd_tcl -force uart-generated-bd.tcl
report_ip_status -file uart-ip-status.rpt
puts "UART_BD_ROUTE_AND_CONSOLE_CHECKS_PASS"
update_compile_order -fileset sources_1
synth_design -rtl -name uart_elaboration
foreach {port pin} {ext_uart_tx E17 ext_uart_rx E18} {
  if {[get_property PACKAGE_PIN [get_ports $port]] ne $pin} {error "wrong UART pad"}
  if {[get_property IOSTANDARD [get_ports $port]] ne "LVCMOS33"} {error "wrong UART voltage constraint"}
}
report_io -file uart-io.rpt
puts "UART_TOP_ELABORATION_AND_3V3_PADS_PASS"
close_project
'''.replace('\\"','"'),encoding='utf-8')
    # Save exact execution text in the short work path (long Tcl paths break some IP tools).
    target=project/'uart_resume.tcl';shutil.copy2(script,target)
    tool='E:/FPGA_Tools/Xilinx/Vivado/2021.1/bin/vivado.bat'
    try:
        with (out/'vivado.log').open('wb') as f:
            completed=subprocess.run([tool,'-mode','batch','-notrace','-source',target.name],cwd=project,stdout=f,stderr=subprocess.STDOUT,timeout=360)
        text=(out/'vivado.log').read_text(errors='replace');r['exit_code']=completed.returncode
        if completed.returncode or not all(s in text for s in ('UART_BD_ROUTE_AND_CONSOLE_CHECKS_PASS','UART_TOP_ELABORATION_AND_3V3_PADS_PASS')):
            raise ValueError('tool validation did not pass')
        for name in ('uart-generated-bd.tcl','uart-ip-status.rpt','uart-io.rpt'):shutil.copy2(project/name,out/name)
        ip=project/'pzp201.gen/sources_1/bd/system/ip/system_sys_ps7_0'
        for name in ('ps7_init.c','ps7_init.h','ps7_init.tcl','ps7_parameters.xml'):shutil.copy2(ip/name,out/name)
        wrappers=list(project.glob('pzp201.gen/**/system_wrapper.v'))
        if len(wrappers)!=1:raise ValueError('wrapper ambiguous')
        shutil.copy2(wrappers[0],out/'system_wrapper.v')
        r.update(status='passed_offline_UART0_EMIO_console_preservation_and_top_elaboration',
            routed_design=False,full_timing_accepted=False,new_boot_image_built=False,
            note='PS init files retained; enabling UART0 requires appropriate PS initialization plus matching PL and DTB. Not a hot-load recipe.')
    except Exception as e:r.update(status='failed_or_incomplete',error=repr(e))
    r['files_sha256']={p.name:sha(p) for p in out.iterdir() if p.is_file() and p.name!='report.json'};save()
    print(out/'report.json');print(r['status'])
    return 0 if r['status'].startswith('passed_') else 1
if __name__=='__main__':raise SystemExit(main())
