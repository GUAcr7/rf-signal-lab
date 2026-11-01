proc simulate_fft {} {
  if {[version -short] ne "2021.1" || [llength $::argv]<4 || [llength $::argv]>5} {error "Expected Vivado 2021.1, project, TB, vectors, evidence, optional stalls 0/1"}
  lassign $::argv project bench vectors evidence
  set stalls 1
  if {[llength $::argv]==5} {set stalls [lindex $::argv 4]}
  if {$stalls ni {0 1}} {error "stalls must be 0 or 1"}
  set project [file normalize $project]
  set bench [file normalize $bench]
  set vectors [file normalize $vectors]
  set evidence [file normalize $evidence]
  foreach name {inputs.hex expected.hex verification.json} {
    if {![file isfile [file join $vectors $name]]} {error "Missing reference $name"}
  }
  file mkdir $evidence
  open_project $project
  set_param general.maxThreads 2
  add_files -fileset sim_1 -norecurse $bench
  set_property top tb_fft1024 [get_filesets sim_1]
  set_property xsim.simulate.runtime all [get_filesets sim_1]
  set options [list -testplusarg "STALLS=$stalls" -testplusarg "INPUTS=[file join $vectors inputs.hex]" \
                    -testplusarg "EXPECTED=[file join $vectors expected.hex]" \
                    -testplusarg "TRACE=[file join $evidence output.csv]" \
                    -testplusarg "METRICS=[file join $evidence cycles.csv]"]
  # Values begin with '-'; use -dict so Vivado does not parse them as
  # set_property command options.
  set_property -dict [list xsim.simulate.xsim.more_options $options] [get_filesets sim_1]
  update_compile_order -fileset sim_1
  launch_simulation -simset sim_1 -mode behavioral
  close_sim
  close_project
  puts "P07_FFT_SIMULATION_RETURNED_REVIEW_SELF_CHECK_AND_TRACE"
}
if {[catch {simulate_fft} problem options]} {
  puts stderr "P07_FFT_SIMULATION_FAILED $problem"
  if {[dict exists $options -errorinfo]} {puts stderr [dict get $options -errorinfo]}
  exit 1
}
exit 0
