# Diagnostic timing analysis of a saved routed design. No implementation,
# checkpoint/bitstream output, programming, register access or board connection.
proc p06_clock_audit {} {
  if {[version -short] ne "2021.1"} { error "Expected Vivado 2021.1" }
  if {[llength $::argv] != 2} { error "Expected routed DCP and new output directory" }
  set dcp [file normalize [lindex $::argv 0]]
  set out [file normalize [lindex $::argv 1]]
  if {![file isfile $dcp] || [file exists $out]} { error "Missing DCP or output already exists" }
  file mkdir $out
  set_param general.maxThreads 1
  open_checkpoint $dcp
  if {[get_property PART [current_design]] ne "xc7z020clg400-2"} { error "Device mismatch" }
  report_clocks -file [file join $out clocks_before.rpt]
  check_timing -verbose -file [file join $out check_timing_before.rpt]
  # The vendor system_project.tcl disables the generated PS7 XDC. Reproduce
  # ONLY its two FCLK clock/jitter definitions on this in-memory diagnostic.
  # Frequencies come from source PS configuration AND generated PS7 XDC.
  # No new timing exceptions or asynchronous groups are assumed here.
  foreach {index period jitter} {0 10.0 0.3 1 5.0 0.15} {
    set pin_name "i_system_wrapper/system_i/sys_ps7/inst/PS7_i/FCLKCLK\[$index\]"
    set pin [get_pins -quiet $pin_name]
    if {[llength $pin] != 1 || [llength [get_clocks -quiet -of_objects $pin]] != 0} { error "Missing or already constrained PS clock: $pin_name" }
    create_clock -name p06_diag_fclk$index -period $period $pin
    set_input_jitter p06_diag_fclk$index $jitter
  }
  report_clocks -file [file join $out clocks_after.rpt]
  check_timing -verbose -file [file join $out check_timing_after.rpt]
  report_timing_summary -delay_type min_max -max_paths 10 -report_unconstrained -file [file join $out timing_with_ps_clocks.rpt]
  report_clock_interaction -file [file join $out clock_interaction.rpt]
  report_cdc -details -file [file join $out cdc.rpt]
  set handle [open [file join $out clock_domain_estimates.tsv] w]
  puts $handle "clock\tperiod_ns\tsetup_slack_ns\thold_slack_ns"
  foreach clock [get_clocks] {
    set setup [get_timing_paths -quiet -from $clock -to $clock -delay_type max -max_paths 1]
    set hold [get_timing_paths -quiet -from $clock -to $clock -delay_type min -max_paths 1]
    set ss "NA"; set hs "NA"
    if {[llength $setup]} { set ss [get_property SLACK [lindex $setup 0]] }
    if {[llength $hold]} { set hs [get_property SLACK [lindex $hold 0]] }
    puts $handle "[get_property NAME $clock]\t[get_property PERIOD $clock]\t$ss\t$hs"
  }
  close $handle
  set handle [open [file join $out scope.txt] w]
  puts $handle "Analysis only. Original DCP/bit/XSA unchanged; no rebuilt hardware or board access."
  puts $handle "Added only source-proven PS FCLK0 100 MHz / FCLK1 200 MHz clocks and generated-XDC jitter."
  puts $handle "Clock relationships, all I/O constraints, actual PS runtime settings and CDC acceptance remain unverified."
  puts $handle "Positive covered slack cannot establish complete timing or board acceptance."
  close $handle
  close_design
  puts "P06_ROUTED_CLOCK_DIAGNOSTIC_COMPLETE $out"
}
if {[catch {p06_clock_audit} problem options]} {
  puts stderr "P06_CLOCK_AUDIT_FAILED $problem"
  if {[dict exists $options -errorinfo]} { puts stderr [dict get $options -errorinfo] }
  exit 1
}
exit 0
