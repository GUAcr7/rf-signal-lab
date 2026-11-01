# Standalone module OOC only. Does not open a hardware target or write a bitstream.
proc implement_fft {} {
  if {[version -short] ne "2021.1" || [llength $::argv]!=1} {error "Expected Vivado 2021.1 and new work directory"}
  set out [file normalize [lindex $::argv 0]]
  if {[file exists $out]} {error "Refusing to reuse FFT implementation directory"}
  file mkdir $out
  create_project fft_ooc [file join $out project] -part xc7z020clg400-2
  set_param general.maxThreads 2
  set_property target_language Verilog [current_project]
  create_ip -name xfft -vendor xilinx.com -library ip -version 9.1 -module_name fft1024_0
  set core [get_ips fft1024_0]
  set_property -dict [list CONFIG.channels {1} CONFIG.transform_length {1024} \
    CONFIG.implementation_options {radix_2_burst_io} CONFIG.target_clock_frequency {100} \
    CONFIG.run_time_configurable_transform_length {false} CONFIG.data_format {fixed_point} \
    CONFIG.input_width {16} CONFIG.phase_factor_width {24} CONFIG.scaling_options {unscaled} \
    CONFIG.rounding_modes {convergent_rounding} CONFIG.aresetn {true} CONFIG.ovflo {false} \
    CONFIG.xk_index {true} CONFIG.throttle_scheme {nonrealtime} CONFIG.output_ordering {natural_order}] $core
  report_property $core -file [file join $out fft_configuration.rpt]
  generate_target all $core
  create_ip_run $core
  launch_runs fft1024_0_synth_1 -jobs 2
  wait_on_run fft1024_0_synth_1
  if {![string match "*Complete*" [get_property STATUS [get_runs fft1024_0_synth_1]]]} {error "FFT synthesis did not complete"}
  open_run fft1024_0_synth_1
  set clocks [get_clocks -of_objects [get_ports aclk]]
  if {[llength $clocks]==0} {
    create_clock -name fft_clk -period 10.000 [get_ports aclk]
  } elseif {[llength $clocks]!=1 || abs([get_property PERIOD $clocks]-10.0)>0.0001} {
    error "Unexpected OOC clock; not silently changing timing target"
  }
  report_clocks -file [file join $out clocks.rpt]
  report_utilization -file [file join $out synthesis_utilization.rpt]
  report_timing_summary -report_unconstrained -file [file join $out synthesis_timing.rpt]
  opt_design
  place_design
  phys_opt_design
  route_design
  report_route_status -file [file join $out route_status.rpt]
  report_utilization -file [file join $out routed_utilization.rpt]
  report_timing_summary -report_unconstrained -file [file join $out routed_timing.rpt]
  report_drc -file [file join $out drc.rpt]
  check_timing -verbose -file [file join $out check_timing.rpt]
  write_checkpoint [file join $out fft1024_routed.dcp]
  close_design
  close_project
  puts "P07_FFT_OOC_IMPLEMENTATION_COMPLETE_NOT_BOARD_INTEGRATION"
}
if {[catch {implement_fft} problem options]} {
  puts stderr "P07_FFT_OOC_FAILED $problem"
  if {[dict exists $options -errorinfo]} {puts stderr [dict get $options -errorinfo]}
  exit 1
}
exit 0
