set_param general.maxThreads 2
cd {E:/p30c-1019-174235}
open_project {E:/p30c-1019-174235/project/combined.xpr}
if {[get_property PART [current_project]] ne "xc7z100ffg900-2"} {error "wrong device"}
if {[get_property PROGRESS [get_runs synth_1]] ne "100%"} {error "synthesis not complete"}
launch_runs impl_1 -to_step route_design -jobs 2
wait_on_run impl_1
set status [get_property STATUS [get_runs impl_1]]
puts "P30_IMPLEMENT_STATUS $status"
if {![string match *route_design*Complete* $status]} {exit 41}
open_run impl_1

set div_c [get_pins -hier -filter {NAME =~ */dual_pixel_24bpp_lvds_mapping_0/inst/parity_flag_reg/C}]
set div_q [get_pins -hier -filter {NAME =~ */dual_pixel_24bpp_lvds_mapping_0/inst/parity_flag_reg/Q}]
if {[llength $div_c] != 1 || [llength $div_q] != 1} {error "divider hierarchy is ambiguous or missing"}
set master [get_clocks -of_objects $div_c]
set derived [get_clocks -of_objects $div_q]
if {[llength $master] != 1 || [llength $derived] != 1 || $derived ne "p29_lvds_half_pclk"} {error "clock model missing or ambiguous"}
set master_period [get_property PERIOD $master]
set derived_period [get_property PERIOD $derived]
if {abs($derived_period-2.0*$master_period) > 0.000001} {error "clock divider ratio changed"}
if {[llength [get_clocks -quiet *clk_wiz_0/inst/clk_in1]] != 0} {error "ClockWiz incorrectly redefines the internal PS FCLK"}
puts "P30_CLOCK_GUARD_PASS master_ns=$master_period divided_ns=$derived_period"
report_utilization -file merged-route-utilization.rpt
report_timing_summary -report_unconstrained -file merged-route-timing.rpt
check_timing -verbose -file merged-route-check-timing.rpt
report_drc -file merged-route-drc.rpt
report_cdc -details -file merged-route-cdc.rpt
report_clocks -file merged-route-clocks.rpt
report_clock_interaction -file merged-route-clock-interaction.rpt
report_bus_skew -warn_on_violation -file merged-route-bus-skew.rpt
report_methodology -file merged-route-methodology.rpt
report_io -file merged-route-io.rpt
write_checkpoint -force merged-route.dcp
report_route_status -file merged-route-status.rpt
# A routed checkpoint is evidence for timing/placement investigation only.
# No write_bitstream, export_hardware, boot image, FPGA programming or board I/O.
puts "P30_IMPLEMENT_COMPLETED"
close_project
exit 0
