set_param general.maxThreads 2
cd {E:/FPGA_Tools/Work/p29-vendor-20261019T082112Z}
open_project {E:/p29d-1019/axi_video_display.xpr}
add_files -fileset constrs_1 -norecurse {E:/p29d-1019/p29_lvds_half_clock.xdc}
set_property PROCESSING_ORDER LATE [get_files {E:/p29d-1019/p29_lvds_half_clock.xdc}]
set directory [file normalize [get_property DIRECTORY [get_runs synth_1]]]
if {![string match -nocase {E:/p29d-1019/*} $directory]} {error "run escaped copied project"}
reset_run synth_1
launch_runs synth_1 -jobs 2
wait_on_run synth_1
if {[get_property PROGRESS [get_runs synth_1]] ne "100%" || ![string match *Complete* [get_property STATUS [get_runs synth_1]]]} {exit 51}
open_run synth_1
set src [get_pins -hier -filter {NAME =~ */dual_pixel_24bpp_lvds_mapping_0/inst/parity_flag_reg/C}]
set dst [get_pins -hier -filter {NAME =~ */dual_pixel_24bpp_lvds_mapping_0/inst/parity_flag_reg/Q}]
set master [get_clocks -of_objects $src]
set divided [get_clocks -of_objects $dst]
if {[llength $master] != 1 || [llength $divided] != 1} {error "ambiguous clocks"}
set in_period [get_property PERIOD $master]
set out_period [get_property PERIOD $divided]
if {abs($out_period-2*$in_period) > 0.001} {error "clock is not /2"}
puts "P29_CLOCK_PERIODS master_ns=$in_period divided_ns=$out_period"
check_timing -verbose -file display-clock-check-timing.rpt
report_timing_summary -file display-clock-timing.rpt
report_clocks -file display-clock-clocks.rpt
report_cdc -details -file display-clock-cdc.rpt
report_drc -file display-clock-drc.rpt
report_utilization -file display-clock-utilization.rpt
write_checkpoint -force display-clock-reviewed.dcp
set f [open display-clock-check-timing.rpt r]
set text [read $f]; close $f
if {![regexp {checking no_clock \(([0-9]+)\)} $text ignored no_clock] || $no_clock != 0} {error "unclocked endpoints remain"}
if {![regexp {checking unconstrained_internal_endpoints \(([0-9]+)\)} $text ignored unconstrained] || $unconstrained != 0} {error "unconstrained internal endpoints remain"}
puts "P29_DISPLAY_CLOCK_MODEL_VERIFIED no_clock=$no_clock unconstrained_internal_endpoints=$unconstrained"
close_project
exit 0
