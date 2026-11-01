open_project pzp201.xpr
open_bd_design [get_files */system.bd]
validate_bd_design
set ps [get_bd_cells sys_ps7]
if {[get_property CONFIG.PCW_UART0_PERIPHERAL_ENABLE $ps] != 1} {error "UART0 disabled"}
if {[get_property CONFIG.PCW_UART0_UART0_IO $ps] ne "EMIO"} {error "UART0 not EMIO"}
if {[get_property CONFIG.PCW_UART1_UART1_IO $ps] ne "MIO 12 .. 13"} {error "console moved"}
foreach {port pin direction} {ext_uart_tx UART0_TX O ext_uart_rx UART0_RX I} {
  set net [get_bd_nets -of_objects [get_bd_ports $port]]
  set expected [get_bd_nets -of_objects [get_bd_pins sys_ps7/$pin]]
  puts "UART_ROUTE port=$port actual=$net expected=$expected"
  puts "UART_PIN_OLD_QUERY [get_bd_pins -of_objects $net -filter "NAME == sys_ps7/$pin"]"
  if {[get_property DIR [get_bd_ports $port]] ne $direction} {error "UART direction"}
  if {[llength $net] != 1 || $net ne $expected} {error "UART disconnected"}
}
write_bd_tcl -force uart-generated-bd.tcl
report_ip_status -file uart-ip-status.rpt
puts "UART_BD_ROUTE_AND_CONSOLE_CHECKS_PASS"
update_compile_order -fileset sources_1

set_param general.maxThreads 2
generate_target all [get_files */system.bd]
launch_runs synth_1 -jobs 2
wait_on_run synth_1
if {[get_property PROGRESS [get_runs synth_1]] ne "100%"} {error "synthesis incomplete"}
puts "UART_FULL_SYNTHESIS_PASS"
launch_runs impl_1 -to_step route_design -jobs 2
wait_on_run impl_1
if {[get_property PROGRESS [get_runs impl_1]] ne "100%"} {error "implementation incomplete"}
open_run impl_1
foreach {port pin} {ext_uart_tx E17 ext_uart_rx E18} {
  if {[get_property PACKAGE_PIN [get_ports $port]] ne $pin} {error "wrong UART pad"}
  if {[get_property IOSTANDARD [get_ports $port]] ne "LVCMOS33"} {error "wrong UART voltage constraint"}
}
report_io -file uart-io.rpt
report_timing_summary -report_unconstrained -file uart-timing.rpt
report_cdc -file uart-cdc.rpt
report_drc -file uart-drc.rpt
check_timing -verbose -file uart-check-timing.rpt
report_utilization -file uart-utilization.rpt
write_checkpoint -force uart-routed.dcp
set f [open uart-run-stats.txt w]
foreach property {STATS.WNS STATS.WHS STATS.TNS STATS.THS STATUS} {
    puts $f "$property=[get_property $property [get_runs impl_1]]"
}
close $f
puts "UART_FULL_ROUTING_AND_3V3_PADS_COMPLETE_NOT_RELEASE"
close_project
