set_param general.maxThreads 2
open_checkpoint {E:/p30c-1019-174235/merged-route.dcp}
set f [open {C:/Users/project_user/Documents/Codex/2026-09-09/2026-fpga-fmql30tai-fpai-python-c/outputs/rf-signal-lab/results/p35-cdc12-cone-20261020T161319Z/cone.txt} w]
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
  puts $f [report_property -all -return_string $cell]
}
puts $f "ALL_COMBINATIONAL_AND_SEQUENTIAL_CONE_CELLS"
foreach c [lsort [all_fanin -flat -to $target -only_cells]] {
  puts $f "CONE_CELL $c REF [get_property REF_NAME $c]"
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
foreach c [lsort [get_cells -hier -filter {REF_NAME == BUFGMUX_CTRL || REF_NAME == BUFR}]] {
  puts $f "CLOCK_CELL $c REF [get_property REF_NAME $c]"
  puts $f [report_property -all -return_string $c]
  foreach p [lsort [get_pins -of_objects $c]] {
    puts $f "  CLOCK_PIN $p CLOCKS [get_clocks -quiet -of_objects $p] NET [get_nets -quiet -of_objects $p]"
  }
}
set launch_clocks [lsort -unique $launch_clocks]
puts $f "UNIQUE_LAUNCH_CLOCKS $launch_clocks"
foreach c $launch_clocks {
  puts $f "LAUNCH_CLOCK_PROPERTY $c"
  puts $f [report_property -all -return_string [get_clocks $c]]
}
close $f
report_clocks -file {C:/Users/project_user/Documents/Codex/2026-09-09/2026-fpga-fmql30tai-fpai-python-c/outputs/rf-signal-lab/results/p35-cdc12-cone-20261020T161319Z/clocks.rpt}
report_clock_interaction -file {C:/Users/project_user/Documents/Codex/2026-09-09/2026-fpga-fmql30tai-fpai-python-c/outputs/rf-signal-lab/results/p35-cdc12-cone-20261020T161319Z/clock-interaction.rpt}
report_cdc -from [get_clocks $launch_clocks] -to [get_clocks -of_objects $dclock] -details -file {C:/Users/project_user/Documents/Codex/2026-09-09/2026-fpga-fmql30tai-fpai-python-c/outputs/rf-signal-lab/results/p35-cdc12-cone-20261020T161319Z/status-cdc.rpt}
write_xdc -force {C:/Users/project_user/Documents/Codex/2026-09-09/2026-fpga-fmql30tai-fpai-python-c/outputs/rf-signal-lab/results/p35-cdc12-cone-20261020T161319Z/checkpoint-export.xdc}
puts "P35_CDC12_CONE_EXTRACTED target=$target launch_clocks=$launch_clocks"
close_design
exit 0
