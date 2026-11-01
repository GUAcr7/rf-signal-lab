source ../scripts/adi_env.tcl
source $ad_hdl_dir/projects/scripts/adi_project_xilinx.tcl
source $ad_hdl_dir/projects/scripts/adi_board.tcl
set p_device xc7z020clg400-2
adi_project pzp201
adi_project_files pzp201 [list system_top.v system_constr.xdc "$ad_hdl_dir/library/common/ad_iobuf.v"]
set_property top system_top [current_fileset]
validate_bd_design
set ps [get_bd_cells sys_ps7]
if {[get_property CONFIG.PCW_UART0_PERIPHERAL_ENABLE $ps] != 1} {error "UART0 disabled"}
if {[get_property CONFIG.PCW_UART0_UART0_IO $ps] ne "EMIO"} {error "UART0 not EMIO"}
if {[get_property CONFIG.PCW_UART1_UART1_IO $ps] ne "MIO 12 .. 13"} {error "console moved"}
foreach {port pin direction} {ext_uart_tx UART0_TX O ext_uart_rx UART0_RX I} {
  if {[get_property DIR [get_bd_ports $port]] ne $direction} {error "UART direction"}
  set net [get_bd_nets -of_objects [get_bd_ports $port]]
  if {[get_bd_pins -of_objects $net -filter "NAME == sys_ps7/$pin"] eq ""} {error "UART disconnected"}
}
write_bd_tcl -force uart-generated-bd.tcl
report_ip_status -file uart-ip-status.rpt
puts "UART_BD_ROUTE_AND_CONSOLE_CHECKS_PASS"
update_compile_order -fileset sources_1
synth_design -rtl -name uart_elaboration
foreach {port pin} {ext_uart_tx E17 ext_uart_rx E18} {
  if {[get_property PACKAGE_PIN [get_ports $port]] ne $pin} {error "wrong UART pad"}
  if {[get_property IOSTANDARD [get_ports $port]] ne "LVCMOS33"} {error "wrong UART voltage constraint"}
}
report_io -file uart-io.rpt
puts "UART_TOP_ELABORATION_AND_3V3_PADS_PASS"
close_project
