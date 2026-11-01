set_param general.maxThreads 2
cd {E:/FPGA_Tools/Work/p29-vendor-20261019T082112Z/rf/src/scripts}
set argc 2
set argv [list xc7z100ffg900-2 {E:/FPGA_Tools/Work/p29-vendor-20261019T082112Z/adi/library}]
if {[catch {source create_project.tcl} reason opts]} {
 puts "P29_RF_CREATE_FAILED $reason"; puts [dict get $opts -errorinfo]; exit 20
}
if {[llength [get_bd_cells -quiet]] < 10} {puts "P29_RF_EMPTY_OR_INCOMPLETE_BD"; exit 21}
validate_bd_design
save_bd_design
set_property top ad_fmcomms3_ebz_xc7z100 [current_fileset]
update_compile_order -fileset sources_1
report_ip_status -file {E:/FPGA_Tools/Work/p29-vendor-20261019T082112Z/rf-ip-status.rpt}
write_bd_tcl -force {E:/FPGA_Tools/Work/p29-vendor-20261019T082112Z/rf-migrated-bd.tcl}
puts "P29_RF_BD_VALIDATED cells=[llength [get_bd_cells -hier]]"
exit 0
