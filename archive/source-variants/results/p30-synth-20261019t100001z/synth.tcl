set_param general.maxThreads 2
cd {E:/p30c-1019-174235}
open_project {E:/p30c-1019-174235/project/combined.xpr}
if {[get_property PART [current_project]] ne "xc7z100ffg900-2"} {error "wrong device"}
generate_target all [get_files *.bd]
update_compile_order -fileset sources_1
if {[get_property PROGRESS [get_runs synth_1]] eq "100%"} {reset_run synth_1}
launch_runs synth_1 -jobs 2
wait_on_run synth_1
set status [get_property STATUS [get_runs synth_1]]
puts "P30_SYNTH_STATUS $status"
if {[get_property PROGRESS [get_runs synth_1]] ne "100%" || ![string match *Complete* $status]} {exit 40}
open_run synth_1
set blackboxes [get_cells -quiet -hier -filter {IS_BLACKBOX == 1}]
if {[llength $blackboxes]} {error "unresolved modules: $blackboxes"}

set div_c [get_pins -hier -filter {NAME =~ */dual_pixel_24bpp_lvds_mapping_0/inst/parity_flag_reg/C}]
set div_q [get_pins -hier -filter {NAME =~ */dual_pixel_24bpp_lvds_mapping_0/inst/parity_flag_reg/Q}]
if {[llength $div_c] != 1 || [llength $div_q] != 1} {error "divider hierarchy is ambiguous or missing"}
set master [get_clocks -of_objects $div_c]
set derived [get_clocks -of_objects $div_q]
if {[llength $master] != 1 || [llength $derived] != 1 || $derived ne "p29_lvds_half_pclk"} {error "clock model missing or ambiguous"}
set master_period [get_property PERIOD $master]
set derived_period [get_property PERIOD $derived]
if {abs($derived_period-2.0*$master_period) > 0.000001} {error "clock divider ratio changed"}
puts "P30_CLOCK_GUARD_PASS master_ns=$master_period divided_ns=$derived_period"
report_utilization -file merged-synth-utilization.rpt
report_timing_summary -report_unconstrained -file merged-synth-timing.rpt
check_timing -verbose -file merged-synth-check-timing.rpt
report_drc -file merged-synth-drc.rpt
report_cdc -details -file merged-synth-cdc.rpt
report_clocks -file merged-synth-clocks.rpt
report_clock_interaction -file merged-synth-clock-interaction.rpt
report_io -file merged-synth-io.rpt
write_checkpoint -force merged-synth.dcp
puts "P30_MERGED_SYNTH_PASS"
close_project
exit 0
