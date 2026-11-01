# A guarded physical-only experiment from the pristine optimized checkpoint.
# Original clocks are preserved; exact source-defined PS clocks are added as in
# the previous baseline. No false paths, asynchronous groups, bitstream or board.
proc p06_reimplement {} {
  if {[version -short] ne "2021.1"} {error "Vivado 2021.1 required"}
  if {[llength $::argv] != 2} {error "Expected original opt DCP and NEW result directory"}
  set source [file normalize [lindex $::argv 0]]
  set out [file normalize [lindex $::argv 1]]
  if {![file isfile $source] || [file exists $out]} {error "Missing input or output already exists"}
  file mkdir $out
  set_param general.maxThreads 2
  open_checkpoint $source
  if {[get_property PART [current_design]] ne "xc7z020clg400-2"} {error "Wrong part"}
  if {[llength [get_cells -hierarchical -filter {IS_BLACKBOX == 1}]] != 0} {error "Unresolved black boxes"}
  report_clocks -file [file join $out original_clocks.rpt]
  foreach {index period jitter} {0 10.0 0.3 1 5.0 0.15} {
    set pin [get_pins -quiet "i_system_wrapper/system_i/sys_ps7/inst/PS7_i/FCLKCLK\[$index\]"]
    if {[llength $pin] != 1 || [llength [get_clocks -quiet -of_objects $pin]] != 0} {error "PS clock endpoint missing or already constrained"}
    create_clock -name p06_derived_fclk$index -period $period $pin
    set_input_jitter p06_derived_fclk$index $jitter
  }
  report_clocks -file [file join $out derived_clocks.rpt]
  write_xdc [file join $out effective_constraints.xdc]
  place_design
  phys_opt_design -directive AggressiveFanoutOpt
  report_timing -from [get_clocks p06_derived_fclk0] -to [get_clocks p06_derived_fclk0] -max_paths 5 -file [file join $out fclk0_before_replication.rpt]
  set data_cells [get_cells -hierarchical -regexp {.*axi_ad9361/inst/i_up_axi/up_wdata_int_reg\[[0-9]+\]}]
  if {[llength $data_cells] != 32} {error "Expected 32 original AD9361 AXI write-data registers"}
  set replicate_nets {}
  set log [open [file join $out replication_sources.txt] w]
  foreach cell $data_cells {
    if {[get_property REF_NAME $cell] ne "FDRE"} {error "Unexpected write-data register primitive"}
    set pin [get_pins -of_objects $cell -filter {REF_PIN_NAME == Q}]
    if {[llength $pin] != 1} {error "Expected exactly one Q output"}
    set net [get_nets -of_objects $pin]
    if {[llength $net] != 1} {error "Expected exactly one driver net"}
    foreach object [list $cell $net] {
      set retained [get_property DONT_TOUCH $object]
      if {$retained ne ""} {
        if {![string is boolean -strict $retained]} {error "Unknown DONT_TOUCH value"}
        if {$retained} {error "Protected register/net; do not override DONT_TOUCH"}
      }
    }
    puts $log "[get_property NAME $cell] [get_property NAME $net]"
    lappend replicate_nets $net
  }
  # Reuse the independently identified reset endpoint; resolve hierarchy segments.
  set endpoint [get_pins -hierarchical -regexp {.*i_tx_channel_1/i_up_dac_channel/i_xfer_cntrl/up_xfer_data_reg\[100\]/R}]
  if {[llength $endpoint] != 1} {error "Expected one reset endpoint"}
  set drivers [get_pins -leaf -of_objects [get_nets -segments -of_objects $endpoint] -filter {DIRECTION == OUT}]
  if {[llength $drivers] != 1} {error "Expected one reset driver"}
  set reset_cell [get_cells -of_objects $drivers]
  set reset_net [get_nets -of_objects $drivers]
  if {[llength $reset_cell] != 1 || [get_property REF_NAME $reset_cell] ne "LUT1" || [llength $reset_net] != 1} {error "Unexpected reset driver"}
  foreach object [list $reset_cell $reset_net] {
    set retained [get_property DONT_TOUCH $object]
    if {$retained ne ""} {
      if {![string is boolean -strict $retained]} {error "Unknown reset DONT_TOUCH value"}
      if {$retained} {error "Protected reset; do not override"}
    }
  }
  puts $log "RESET [get_property NAME $reset_cell] [get_property NAME $reset_net]"
  close $log
  lappend replicate_nets $reset_net
  phys_opt_design -force_replication_on_nets $replicate_nets
  route_design
  report_route_status -file [file join $out route_status.rpt]
  report_utilization -file [file join $out utilization.rpt]
  check_timing -verbose -file [file join $out check_timing_after.rpt]
  report_timing_summary -delay_type min_max -max_paths 10 -report_unconstrained -file [file join $out routed_timing.rpt]
  report_clock_interaction -file [file join $out clock_interaction.rpt]
  report_timing -from [get_clocks p06_derived_fclk0] -to [get_clocks p06_derived_fclk0] -delay_type max -max_paths 10 -file [file join $out fclk0_internal_setup.rpt]
  report_cdc -details -file [file join $out cdc.rpt]
  report_drc -file [file join $out drc.rpt]
  report_methodology -file [file join $out methodology.rpt]
  write_checkpoint [file join $out derived_routed.dcp]
  set handle [open [file join $out scope.txt] w]
  puts $handle "Physical register/reset replication only; pristine source DCP and original HDL unchanged."
  puts $handle "100/200 MHz PS clocks and jitter match prior exact generated source definitions. No timing exceptions."
  puts $handle "No bitstream, XSA, programming, RF or board access. I/O/CDC acceptance still pending."
  close $handle
  close_design
  puts "P06_CONTROL_REPLICATION_EXPERIMENT_COMPLETE"
}
if {[catch {p06_reimplement} problem options]} {
  puts stderr "P06_CONTROL_REPLICATION_FAILED $problem"
  if {[dict exists $options -errorinfo]} {puts stderr [dict get $options -errorinfo]}
  exit 1
}
exit 0
