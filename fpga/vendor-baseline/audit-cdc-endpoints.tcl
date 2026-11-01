# Read-only netlist inspection. Never modifies clocks, exceptions or design.
proc p06_audit {} {
  if {[version -short] ne "2021.1" || [llength $::argv] != 2} {error "Expected Vivado 2021.1, routed DCP and new directory"}
  set source [file normalize [lindex $::argv 0]]
  set out [file normalize [lindex $::argv 1]]
  if {![file isfile $source] || [file exists $out]} {error "Missing DCP or output exists"}
  file mkdir $out
  set_param general.maxThreads 2
  open_checkpoint $source
  set handle [open [file join $out failing_endpoints.tsv] w]
  puts $handle "from_clock\tto_clock\tslack_ns\tstartpoint\tendpoint"
  foreach {from to} {rx_clk p06_derived_fclk0 p06_derived_fclk0 rx_clk} {
    set source_clock [get_clocks $from]
    set destination_clock [get_clocks $to]
    if {[llength $source_clock] != 1 || [llength $destination_clock] != 1} {error "Expected known derived clock names"}
    set paths [get_timing_paths -from $source_clock -to $destination_clock -slack_lesser_than 0 -max_paths 2000 -nworst 1]
    foreach path $paths {
      puts $handle "$from\t$to\t[get_property SLACK $path]\t[get_property STARTPOINT_PIN $path]\t[get_property ENDPOINT_PIN $path]"
    }
    report_timing -from $source_clock -to $destination_clock -max_paths 20 -file [file join $out "${from}_to_${to}.rpt"]
  }
  close $handle
  report_exceptions -coverage -file [file join $out exception_coverage.rpt]
  report_clocks -file [file join $out clocks.rpt]
  check_timing -verbose -file [file join $out check_timing.rpt]
  report_cdc -details -file [file join $out cdc.rpt]
  close_design
  puts "P06_CDC_ENDPOINT_AUDIT_COMPLETE"
}
if {[catch {p06_audit} problem options]} {
  puts stderr "P06_CDC_AUDIT_FAILED $problem"
  if {[dict exists $options -errorinfo]} {puts stderr [dict get $options -errorinfo]}
  exit 1
}
exit 0
