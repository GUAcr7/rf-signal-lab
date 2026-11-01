# Derived experiment only. Use an original optimized checkpoint, add the exact
# source-defined PS clocks, then place/route again. No timing exceptions, bitstream,
# XSA, programming, board access, or changes to the vendor source tree.
proc p06_reimplement {} {
  if {[version -short] ne "2021.1"} { error "Vivado 2021.1 required" }
  if {[llength $::argv] != 2} { error "Expected original opt DCP and NEW result directory" }
  set source [file normalize [lindex $::argv 0]]
  set out [file normalize [lindex $::argv 1]]
  if {![file isfile $source] || [file exists $out]} { error "Missing input or output already exists" }
  file mkdir $out
  set_param general.maxThreads 2
  open_checkpoint $source
  if {[get_property PART [current_design]] ne "xc7z020clg400-2"} { error "Wrong part" }
  if {[llength [get_cells -hierarchical -filter {IS_BLACKBOX == 1}]] != 0} { error "Unresolved black boxes" }
  report_clocks -file [file join $out original_clocks.rpt]
  foreach {index period jitter} {0 10.0 0.3 1 5.0 0.15} {
    set pin [get_pins -quiet "i_system_wrapper/system_i/sys_ps7/inst/PS7_i/FCLKCLK\[$index\]"]
    if {[llength $pin] != 1 || [llength [get_clocks -quiet -of_objects $pin]] != 0} { error "PS clock endpoint missing or already constrained" }
    create_clock -name p06_derived_fclk$index -period $period $pin
    set_input_jitter p06_derived_fclk$index $jitter
  }
  report_clocks -file [file join $out derived_clocks.rpt]
  check_timing -verbose -file [file join $out check_timing_before.rpt]
  write_xdc [file join $out effective_constraints.xdc]
  place_design
  report_timing_summary -delay_type min_max -max_paths 5 -file [file join $out placed_timing.rpt]
  phys_opt_design -directive AggressiveFanoutOpt
  set endpoint [get_pins -hierarchical -regexp {.*i_tx_channel_1/i_up_dac_channel/i_xfer_cntrl/up_xfer_data_reg\[100\]/R}]
  if {[llength $endpoint] != 1} {error "Expected one previously failing reset endpoint"}
  # An endpoint-local hierarchical segment need not contain the primitive driver.
  # Resolve all connected segments, then select the leaf primitive output.
  set reset_segments [get_nets -segments -of_objects $endpoint]
  if {[llength $reset_segments] == 0} {error "Expected reset net segments"}
  set source_pin [get_pins -leaf -of_objects $reset_segments -filter {DIRECTION == OUT}]
  if {[llength $source_pin] != 1} {error "Expected one leaf reset driver pin"}
  set reset_net [get_nets -of_objects $source_pin]
  if {[llength $reset_net] != 1} {error "Expected one reset driver segment"}
  set source_cell [get_cells -of_objects $source_pin]
  if {[llength $source_cell] != 1 || [get_property REF_NAME $source_cell] ne "LUT1"} {error "Expected original reset inverter driver"}
  if {[get_property DONT_TOUCH $source_cell] || [get_property DONT_TOUCH $reset_net]} {error "Reset replication blocked by retained DONT_TOUCH; do not override"}
  report_property $reset_net -file [file join $out reset_net_before.rpt]
  report_property $source_cell -file [file join $out reset_driver_before.rpt]
  phys_opt_design -force_replication_on_nets $reset_net
  route_design
  report_route_status -file [file join $out route_status.rpt]
  report_utilization -file [file join $out utilization.rpt]
  check_timing -verbose -file [file join $out check_timing_after.rpt]
  report_timing_summary -delay_type min_max -max_paths 10 -report_unconstrained -file [file join $out routed_timing.rpt]
  report_clock_interaction -file [file join $out clock_interaction.rpt]
  report_timing -from [get_clocks p06_derived_fclk0] -to [get_clocks p06_derived_fclk0] -delay_type max -max_paths 5 -file [file join $out fclk0_internal_setup.rpt]
  report_cdc -details -file [file join $out cdc.rpt]
  report_drc -file [file join $out drc.rpt]
  report_methodology -file [file join $out methodology.rpt]
  write_checkpoint [file join $out derived_routed.dcp]
  set h [open [file join $out scope.txt] w]
  puts $h "Derived implementation; original HDL and original checkpoints unchanged. No bitstream/XSA or board access."
  puts $h "Only original generated-PS-XDC clock and jitter definitions added. No false paths or asynchronous clock groups added."
  puts $h "I/O timing and clock-domain crossing acceptance still require interface-specific evidence. This is not board qualification."
  close $h
  close_design
  puts "P06_DERIVED_PS_CLOCK_IMPLEMENTATION_COMPLETE"
}
if {[catch {p06_reimplement} problem options]} {
  puts stderr "P06_DERIVED_IMPLEMENTATION_FAILED $problem"
  if {[dict exists $options -errorinfo]} { puts stderr [dict get $options -errorinfo] }
  exit 1
}
exit 0


