set_param general.maxThreads 2
cd {E:/p30c-1019-173830}
create_project combined {E:/p30c-1019-173830/project} -part xc7z100ffg900-2
set_property target_language Verilog [current_project]
set_property ip_repo_paths {E:/FPGA_Tools/Work/p29-vendor-20261019T082112Z/adi/library} [current_project]
update_ip_catalog
add_files [glob hdl/*.v]
add_files -fileset constrs_1 [glob constraints/*.xdc]
set_property PROCESSING_ORDER LATE [get_files */half_clock.xdc]
source combined_bd.tcl
validate_bd_design
save_bd_design
set_property top rf_display_top [current_fileset]
update_compile_order -fileset sources_1
write_bd_tcl -force merged-bd.tcl
report_ip_status -file merged-ip-status.rpt
if {[llength [get_bd_cells -filter {VLNV =~ *processing_system7*}]] != 1} {error "expected one PS7"}
if {[get_property CONFIG.PCW_GPIO_EMIO_GPIO_WIDTH [get_bd_cells sys_ps7]] != 64} {error "EMIO mapping lost"}
if {[get_property CONFIG.NUM_PORTS [get_bd_cells sys_concat_intc]] != 16} {error "IRQ width changed"}
puts "P30_MERGED_BD_VALIDATED cells=[llength [get_bd_cells -hier]]"
close_project
exit 0
