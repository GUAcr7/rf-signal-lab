set_param general.maxThreads 2
cd {E:/p30c-1019-174235}
open_project {E:/p30c-1019-174235/project/combined.xpr}
if {[get_property PART [current_project]] ne "xc7z100ffg900-2"} {error "wrong device"}
generate_target all [get_files *.bd]
update_compile_order -fileset sources_1
launch_runs synth_1 -jobs 2
wait_on_run synth_1
set status [get_property STATUS [get_runs synth_1]]
puts "P30_SYNTH_STATUS $status"
if {[get_property PROGRESS [get_runs synth_1]] ne "100%" || ![string match *Complete* $status]} {exit 40}
open_run synth_1
set blackboxes [get_cells -quiet -hier -filter {IS_BLACKBOX == 1}]
if {[llength $blackboxes]} {error "unresolved modules: $blackboxes"}
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
