set_param general.maxThreads 2
cd {E:/FPGA_Tools/Work/p29-vendor-20261019T082112Z}
open_project {E:/p29d-1019/axi_video_display.xpr}
if {[get_property PART [current_project]] ne "xc7z100ffg900-2"} {error "wrong part"}
set expected_root [file normalize {E:/p29d-1019}]
foreach run [get_runs] {
    set directory [file normalize [get_property DIRECTORY $run]]
    if {![string match -nocase ${expected_root}/* $directory]} {error "run directory escaped copied short project: $directory"}
}
set tpg [get_runs *v_tpg*_synth_1]
if {[llength $tpg] != 1} {error "expected one TPG synthesis run"}
reset_run $tpg
reset_run synth_1
puts "P29_SHORT_PATH_RECOVERY $expected_root"

set bd [get_files *.bd]
generate_target all $bd
update_compile_order -fileset sources_1
launch_runs synth_1 -jobs 2
wait_on_run synth_1
set status [get_property STATUS [get_runs synth_1]]
puts "P29_DISPLAY_SYNTH_STATUS $status"
if {[get_property PROGRESS [get_runs synth_1]] ne "100%" || ![string match *Complete* $status]} {exit 40}
open_run synth_1
report_utilization -file display-synth-utilization.rpt
report_timing_summary -file display-synth-timing.rpt
check_timing -verbose -file display-synth-check-timing.rpt
write_checkpoint -force display-synth.dcp
puts "P29_DISPLAY_SYNTH_PASS"
close_project
exit 0
