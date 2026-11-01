set expected xc7z100ffg900-2
puts "P27_TOOL [version -short]"
puts "P27_Z100_PARTS [get_parts -quiet xc7z100*]"
puts "P27_Z020_PARTS [get_parts -quiet xc7z020*]"
help get_parts
puts "P27_PART_COUNT [llength [get_parts -quiet $expected]]"
if {![llength [get_parts -quiet $expected]]} { puts "P27_PART_MISSING"; exit 3 }
create_project -in_memory -part $expected
read_verilog probe.v
if {[catch {synth_design -top license_probe -part $expected} reason]} {
    puts "P27_SYNTHESIS_BLOCKED $reason"
    exit 4
}
puts "P27_SYNTHESIS_CAPABILITY_PASS"
exit 0
