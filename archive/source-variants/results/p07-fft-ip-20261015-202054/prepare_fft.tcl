# Standalone FFT candidate, not integrated/programmed. Inspect the generated
# interfaces and license before using it in a self-checking simulation.
proc prepare_fft {} {
  if {[version -short] ne "2021.1" || [llength $::argv] != 1} {error "Vivado 2021.1 and new work directory required"}
  set out [file normalize [lindex $::argv 0]]
  if {[file exists $out]} {error "FFT work directory already exists"}
  file mkdir $out
  create_project fft_reference [file join $out project] -part xc7z020clg400-2
  set_property target_language Verilog [current_project]
  set_property simulator_language Mixed [current_project]
  set_param general.maxThreads 2
  create_ip -name xfft -vendor xilinx.com -library ip -version 9.1 -module_name fft1024_0
  set core [get_ips fft1024_0]
  set_property -dict [list CONFIG.channels {1} CONFIG.transform_length {1024} \
    CONFIG.implementation_options {radix_2_burst_io} CONFIG.target_clock_frequency {100} \
    CONFIG.target_data_throughput {1} CONFIG.run_time_configurable_transform_length {false} \
    CONFIG.data_format {fixed_point} CONFIG.input_width {16} CONFIG.phase_factor_width {24} \
    CONFIG.scaling_options {unscaled} CONFIG.rounding_modes {convergent_rounding} \
    CONFIG.aresetn {true} CONFIG.ovflo {false} CONFIG.xk_index {true} \
    CONFIG.throttle_scheme {nonrealtime} CONFIG.output_ordering {natural_order}] $core
  report_property $core -file [file join $out fft_configuration.rpt]
  generate_target all $core
  export_ip_user_files -of_objects $core -no_script -sync -force
  report_ip_status -file [file join $out ip_status.rpt]
  set handle [open [file join $out scope.txt] w]
  puts $handle "Standalone FFT IP configuration/output-products only. No board, bitstream, retune or deployment."
  puts $handle "1024 points, signed16 I/Q, 24-bit phase, radix2 burst, unscaled, convergent rounding, natural output, 100MHz target."
  close $handle
  close_project
  puts "P07_FFT_IP_PREPARATION_COMPLETE"
}
if {[catch {prepare_fft} problem options]} {
  puts stderr "P07_FFT_PREPARATION_FAILED $problem"
  if {[dict exists $options -errorinfo]} {puts stderr [dict get $options -errorinfo]}
  exit 1
}
exit 0
