# Run only from the freshly prepared workspace. No implementation/board access.
proc p07_synth_only {} {
  if {[version -short] ne "2021.1"} { error "P07 requires exactly Vivado 2021.1" }
  set part "xc7z020clg400-2"
  if {[llength [get_parts -quiet $part]] != 1} { error "P07 required device is unavailable: $part" }
  set root [file normalize [file dirname [info script]]]
  if {[file normalize [pwd]] ne $root} { error "Run from the prepared short workspace root" }
  set reports [file join $root reports]
  file mkdir $reports
  foreach name {utilization.rpt utilization_hierarchical.rpt timing_summary.rpt internal_setup.rpt internal_hold.rpt check_timing.rpt clocks.rpt unconstrained_io.rpt synth.dcp internal_metrics.tsv} {
    if {[file exists [file join $reports $name]]} { error "Refusing to overwrite an existing result: $name" }
  }
  set coefficient_file [file join $root fpga ip fir63_q17.hex]
  set handle [open $coefficient_file r]
  set coefficients [split [string trim [read $handle]] "\n"]
  close $handle
  if {[llength $coefficients] != 63} { error "Exactly 63 coefficients are required" }
  foreach word $coefficients {
    if {![regexp {^[0-3][[:xdigit:]]{4}$} [string trim $word]]} { error "Invalid 18-bit coefficient word" }
  }
  if {![regexp {[1-9a-fA-F]} [join $coefficients ""]]} { error "All coefficients are zero" }
  # These overrides are irrelevant to this independent RTL flow and must be absent.
  foreach name {ADI_HDL_DIR ADI_GHDL_DIR ADI_IGNORE_VERSION_CHECK ADI_USE_OOC_SYNTHESIS ADI_USE_INCR_COMP ADI_POWER_OPTIMIZATION ADI_NO_BITSTREAM_COMPRESSION ADI_GENERATE_UTILIZATION ADI_GENERATE_XPA ADI_MAX_OOC_JOBS ADI_VIVADO_IP_LIBRARY ADI_DISABLE_MESSAGE_SUPPRESION} {
    if {[info exists ::env($name)]} { error "Unexpected optional environment override: $name" }
  }
  if {![info exists ::env(REQUIRED_VIVADO_VERSION)] || $::env(REQUIRED_VIVADO_VERSION) ne "2021.1"} { error "Required version environment must equal 2021.1" }
  puts "P07_TOOL_VERSION [version -short]"
  puts "P07_DEVICE $part"
  puts "P07_SCOPE standalone OOC synthesis; no placement, routing, bitstream or board"
  # This parameter affects only this Vivado process, not saved/global settings.
  set_param general.maxThreads 1
  create_project -in_memory p07_fir_ooc -part $part
  read_verilog [file join $root fpga rtl fixed_fir_iq.v]
  read_xdc [file join $root fir_internal_100mhz.xdc]
  # Preserve the original COEFF_FILE default, resolved against this root.
  synth_design -top fixed_fir_iq -part $part -mode out_of_context -generic N_TAPS=63
  if {[get_property PART [current_design]] ne $part} { error "Synthesized device mismatch" }
  if {[llength [get_cells -quiet -hierarchical -filter {IS_BLACKBOX == 1}]] != 0} { error "Unresolved synthesis black box" }
  set clock [get_clocks -quiet fir_clk]
  if {[llength $clock] != 1 || abs([get_property PERIOD $clock]-10.0) > 0.000001} { error "Missing 10 ns clock constraint" }
  if {[llength [all_registers]] == 0} { error "Synthesis removed every register; refusing a vacuous timing result" }
  set data_ports [get_ports -quiet {m_i* m_q*}]
  if {[llength $data_ports] != 32} { error "Expected both 16-bit data output ports" }
  foreach port $data_ports {
    set drivers [get_pins -quiet -of_objects [get_nets -quiet -of_objects $port] -filter {DIRECTION == OUT}]
    if {[llength $drivers] == 0} { error "Undriven data output: $port" }
    foreach cell [get_cells -quiet -of_objects $drivers] {
      if {[get_property REF_NAME $cell] in {GND VCC}} { error "Constant data output: $port; inspect coefficient initialization" }
    }
  }
  set setup [get_timing_paths -from $clock -to $clock -delay_type max -max_paths 1]
  set hold [get_timing_paths -from $clock -to $clock -delay_type min -max_paths 1]
  if {[llength $setup] != 1 || [llength $hold] != 1} { error "No internal clock-to-clock timing path" }
  report_utilization -file [file join $reports utilization.rpt]
  report_utilization -hierarchical -file [file join $reports utilization_hierarchical.rpt]
  report_timing_summary -delay_type min_max -max_paths 10 -report_unconstrained -file [file join $reports timing_summary.rpt]
  report_timing -from $clock -to $clock -delay_type max -max_paths 10 -file [file join $reports internal_setup.rpt]
  report_timing -from $clock -to $clock -delay_type min -max_paths 10 -file [file join $reports internal_hold.rpt]
  check_timing -verbose -file [file join $reports check_timing.rpt]
  report_clocks -file [file join $reports clocks.rpt]
  set handle [open [file join $reports unconstrained_io.rpt] w]
  puts $handle "Scope: synthesis internal register timing at 100 MHz only."
  puts $handle "Input/output delays and external reset/handshake timing are intentionally unspecified."
  puts $handle "No timing exceptions, external drive/load, pin assignments, board or ADC timing assumptions."
  puts $handle "check_timing/timing_summary may therefore report unconstrained I/O; inspect them explicitly."
  close $handle
  write_checkpoint [file join $reports synth.dcp]
  set setup_slack [get_property SLACK [lindex $setup 0]]
  set hold_slack [get_property SLACK [lindex $hold 0]]
  set handle [open [file join $reports internal_metrics.tsv] w]
  foreach {key value} [list tool_version [version -short] part $part top fixed_fir_iq taps 63 clock_period_ns 10.0 setup_slack_ns $setup_slack hold_slack_ns $hold_slack internal_setup_estimate_nonnegative [expr {$setup_slack >= 0}] internal_hold_estimate_nonnegative [expr {$hold_slack >= 0}] register_cells [llength [all_registers]] placed false routed false timing_closed false board_accessed false] {
    puts $handle "$key\t$value"
  }
  close $handle
  puts "P07_SYNTHESIS_REPORTS_COMPLETE setup_estimate_ns=$setup_slack hold_estimate_ns=$hold_slack"
  puts "P07_NOT_IMPLEMENTED estimated slack is not routed timing or measured board performance"
}
if {[catch {p07_synth_only} problem options]} {
  puts stderr "P07_SYNTHESIS_FAILED $problem"
  if {[dict exists $options -errorinfo]} { puts stderr [dict get $options -errorinfo] }
  exit 1
}
exit 0
