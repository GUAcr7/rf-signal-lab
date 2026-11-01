set_param general.maxThreads 2
cd {E:/FPGA_Tools/Work/p29-vendor-20261019T082112Z}
open_project {E:/FPGA_Tools/Work/p29-vendor-20261019T082112Z/rf/runs/ad-fmcomms3-ebz-xc7z100.xpr}
if {[get_property PART [current_project]] ne "xc7z100ffg900-2"} {error "wrong part"}
set bd [get_files *.bd]
generate_target all $bd
update_compile_order -fileset sources_1
launch_runs synth_1 -jobs 2
wait_on_run synth_1
set status [get_property STATUS [get_runs synth_1]]
puts "P29_RF_SYNTH_STATUS $status"
if {[get_property PROGRESS [get_runs synth_1]] ne "100%" || ![string match *Complete* $status]} {exit 40}
open_run synth_1
report_utilization -file rf-synth-utilization.rpt
report_timing_summary -file rf-synth-timing.rpt
check_timing -verbose -file rf-synth-check-timing.rpt
write_checkpoint -force rf-synth.dcp
puts "P29_RF_SYNTH_PASS"
close_project
exit 0
