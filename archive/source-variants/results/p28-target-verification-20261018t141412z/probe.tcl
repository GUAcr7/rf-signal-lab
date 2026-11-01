set target xc7z100ffg900-2
puts "P28_TOOL [version -short]"
puts "P28_Z020_PARTS [get_parts -quiet xc7z020clg400-2]"
puts "P28_Z100_PARTS [get_parts -quiet $target]"
if {![llength [get_parts -quiet $target]]} {puts "P28_DEVICE_MISSING"; exit 3}
set_param general.maxThreads 2
create_project -in_memory -part $target
read_verilog probe.v
if {[catch {synth_design -top license_probe -part $target} reason]} {
  puts "P28_SYNTHESIS_BLOCKED $reason"
  exit 4
}
report_utilization -file probe-utilization.rpt
write_checkpoint probe-synth.dcp
puts "P28_TARGET_SYNTHESIS_PASS"
exit 0
