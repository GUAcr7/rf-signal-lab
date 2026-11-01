set_param general.maxThreads 2
cd {E:/p30c-1019-174235}
open_project {E:/p30c-1019-174235/project/combined.xpr}
open_bd_design [get_files *.bd]
set wizard [get_bd_cells clk_wiz_0]
set before [get_property CONFIG.PRIM_SOURCE $wizard]
if {$before ne "Single_ended_clock_capable_pin"} {error "unexpected baseline: $before"}
set_property CONFIG.PRIM_SOURCE No_buffer $wizard
validate_bd_design
save_bd_design
generate_target all [get_files *.bd]
write_bd_tcl -force merged-bd.tcl
puts "P30_CLOCK_SOURCE_CORRECTED before=$before after=[get_property CONFIG.PRIM_SOURCE $wizard]"
close_project
exit 0
