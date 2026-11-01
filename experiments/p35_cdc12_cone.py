"""Read an existing routed DCP and expose the TX busy-status CDC12 cone.

No source, constraint, design, bitstream, project, or board changes. All outputs
are independent diagnostic files; the old checkpoint SHA must remain unchanged.
"""
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
DCP=Path('E:/p30c-1019-174235/merged-route.dcp')
LIB=Path('E:/FPGA_Tools/Work/p29-vendor-20261019T082112Z/adi/library')

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p35-cdc12-cone-%Y%m%dT%H%M%SZ')
    out.mkdir(exist_ok=False)
    protected=[DCP,Path('E:/p30c-1019-174235/project/combined.xpr'),
        LIB/'axi_dmac/request_arb.v',LIB/'util_axis_fifo/util_axis_fifo.v',
        LIB/'util_cdc/sync_bits.v',LIB/'util_clkdiv/util_clkdiv.v',
        LIB/'util_clkdiv/util_clkdiv_constr.xdc']
    before={str(p):sha(p) for p in protected}
    report=dict(status='running',board_operations=False,RTL_changes=False,
        constraint_changes=False,project_saved=False,dcp=str(DCP),hashes_before=before)
    def save():(out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    save()
    # Use [format] for bit-indexed names so Tcl does not execute square brackets.
    script=r'''set_param general.maxThreads 2
open_checkpoint {@DCP@}
set f [open {@OUT@/cone.txt} w]
set b i_system_wrapper/axi_ad9361_dac_dma/inst/i_request_arb
set wanted [format {%s/i_sync_status_dest/cdc_sync_stage1_reg[1]/D} $b]
set target [get_pins -quiet $wanted]
if {[llength $target] != 1} {error "target not unique $wanted $target"}
puts $f "TARGET $target"
set destination [get_cells -of_objects $target]
puts $f [report_property -all -return_string $destination]
set dclock [get_pins -of_objects $destination -filter {REF_PIN_NAME == C}]
puts $f "DESTINATION_C $dclock CLOCKS [get_clocks -of_objects $dclock]"
set starts [all_fanin -flat -to $target -startpoints_only]
puts $f "STARTPOINT_COUNT [llength $starts]"
set launch_clocks {}
foreach sp [lsort $starts] {
  set cell [get_cells -quiet -of_objects $sp]
  set cp [get_pins -quiet -of_objects $cell -filter {REF_PIN_NAME == C}]
  set clks [get_clocks -quiet -of_objects $cp]
  foreach c $clks {lappend launch_clocks $c}
  puts $f "STARTPOINT $sp CELL $cell REF [get_property REF_NAME $cell] CLOCKPINS $cp CLOCKS $clks"
  set csegments [get_nets -quiet -segments -of_objects $cp]
  puts $f "CLOCK_NET_LEAF_DRIVER [get_pins -quiet -leaf -of_objects $csegments -filter {DIRECTION == OUT}]"
  puts $f [report_property -all -return_string $cell]
}
puts $f "ALL_COMBINATIONAL_AND_SEQUENTIAL_CONE_CELLS"
foreach c [lsort [all_fanin -flat -to $target -only_cells]] {
  puts $f "CONE_CELL $c REF [get_property REF_NAME $c]"
  if {[string match LUT* [get_property REF_NAME $c]]} {
    puts $f "LUT_INIT [get_property INIT $c]"
    foreach p [get_pins -of_objects $c -filter {DIRECTION == IN}] {
      puts $f "LUT_INPUT $p STARTPOINTS [all_fanin -flat -to $p -startpoints_only]"
    }
  }
  foreach p [lsort [get_pins -of_objects $c -filter {DIRECTION == IN}]] {
    puts $f "  PIN $p NET [get_nets -quiet -of_objects $p] DRIVER [get_pins -quiet -of_objects [get_nets -quiet -of_objects $p] -filter {DIRECTION == OUT}]"
  }
}
puts $f "RADDR_SYNCHRONIZER_CHAIN"
set chain [get_cells -hier -filter {NAME =~ *axi_ad9361_dac_dma/inst/i_request_arb/i_dest_response_fifo/i_raddr_sync/*}]
foreach c [lsort $chain] {
  set dp [get_pins -quiet -of_objects $c -filter {REF_PIN_NAME == D}]
  set cp [get_pins -quiet -of_objects $c -filter {REF_PIN_NAME == C}]
  puts $f "CHAIN_CELL $c REF [get_property REF_NAME $c] C $cp CLOCKS [get_clocks -quiet -of_objects $cp]"
  puts $f [report_property -all -return_string $c]
  if {[llength $dp]} {
    foreach sp [all_fanin -flat -to $dp -startpoints_only] {
      set sc [get_cells -quiet -of_objects $sp]
      set cpin [get_pins -quiet -of_objects $sc -filter {REF_PIN_NAME == C}]
      puts $f "  D_STARTPOINT $sp CELL $sc C $cpin CLOCKS [get_clocks -quiet -of_objects $cpin]"
    }
  }
}
puts $f "MUX_AND_DIVIDER_CLOCKS"
foreach c [lsort [get_cells -hier -filter {REF_NAME == BUFGMUX_CTRL || REF_NAME == BUFGCTRL || REF_NAME == BUFR}]] {
  puts $f "CLOCK_CELL $c REF [get_property REF_NAME $c]"
  puts $f [report_property -all -return_string $c]
  foreach p [lsort [get_pins -of_objects $c]] {
    puts $f "  CLOCK_PIN $p CLOCKS [get_clocks -quiet -of_objects $p] NET [get_nets -quiet -of_objects $p]"
    if {[get_property DIRECTION $p] eq "IN"} {
      puts $f "  CLOCK_PIN_FANIN $p STARTPOINTS [all_fanin -flat -to $p -startpoints_only]"
    }
  }
}
set launch_clocks [lsort -unique $launch_clocks]
puts $f "UNIQUE_LAUNCH_CLOCKS $launch_clocks"
foreach c $launch_clocks {
  puts $f "LAUNCH_CLOCK_PROPERTY $c"
  puts $f [report_property -all -return_string [get_clocks $c]]
}
close $f
report_clocks -file {@OUT@/clocks.rpt}
report_clock_interaction -file {@OUT@/clock-interaction.rpt}
report_cdc -from [get_clocks $launch_clocks] -to [get_clocks -of_objects $dclock] -details -file {@OUT@/status-cdc.rpt}
write_xdc -force {@OUT@/checkpoint-export.xdc}
puts "P35_CDC12_CONE_EXTRACTED target=$target launch_clocks=$launch_clocks"
close_design
exit 0
'''.replace('@DCP@',DCP.as_posix()).replace('@OUT@',out.as_posix())
    tcl=out/'inspect.tcl';tcl.write_text(script,encoding='utf-8',newline='\n')
    argv=['E:/FPGA_Tools/Xilinx/Vivado/2021.1/bin/vivado.bat','-mode','batch','-notrace',
        '-source',str(tcl),'-log',str(out/'vivado.log'),'-journal',str(out/'vivado.jou')]
    report['argv']=argv
    (out/'executed-runner.py').write_bytes(Path(__file__).read_bytes())
    env=os.environ.copy();env['XILINXD_LICENSE_FILE']='E:/FPGA_Tools/Downloads/Xilinx.lic'
    save()
    try:
        with (out/'stdout.txt').open('wb') as log:
            process=subprocess.Popen(argv,cwd=out,stdout=log,stderr=subprocess.STDOUT,env=env)
            try:
                rc=process.wait(timeout=180)
            except subprocess.TimeoutExpired:
                subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True)
                process.wait(timeout=30)
                raise
        report['exit_code']=rc
        text=(out/'stdout.txt').read_text('utf-8',errors='replace')
        report['markers']=[s for s in text.splitlines() if s.startswith('P35_')]
        report['errors']=[s for s in text.splitlines() if s.startswith('ERROR:')]
        report['status']='passed_read_only_cone_extraction_not_CDC_closure' if rc==0 and report['markers'] and not report['errors'] else 'failed'
    except Exception as exc:
        report.update(status='failed',error=repr(exc))
    finally:
        report['hashes_after']={str(p):sha(p) for p in protected}
        report['protected_inputs_unchanged']=report['hashes_after']==before
        if not report['protected_inputs_unchanged']:report['status']='failed_inputs_changed'
        report['artifacts']=[dict(file=p.name,sha256=sha(p),bytes=p.stat().st_size)
            for p in out.iterdir() if p.is_file() and p.name!='report.json']
        save();print(out,flush=True);print(report['status'],flush=True)
    return 0 if report['status'].startswith('passed_') else 1

if __name__=='__main__':raise SystemExit(main())
