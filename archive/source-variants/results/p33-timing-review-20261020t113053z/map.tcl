open_checkpoint E:/p30c-1019-174235/merged-route.dcp
set fp [open clock-port-map.txt w]
foreach port [list rx_clk_in_p tx_clk_out_p lcd_pclk o_video_pclk {lvds_clk_out_p[0]} {lvds_clk_out_p[1]}] {
  puts $fp "PORT $port CLOCKS [get_clocks -quiet -of_objects [get_ports $port]]"
  puts $fp "STARTPOINTS [all_fanin -quiet -flat -startpoints_only -to [get_ports $port]]"
}
foreach pattern [list *i_rx_clk* *i_tx_clk* *i_rx_data_iddr* *i_tx_data_oddr* *i_tx_frame* *i_rx_frame*] {
  foreach cell [get_cells -quiet -hier -filter "NAME =~ $pattern"] {
    puts $fp "CELL $cell REF [get_property REF_NAME $cell]"
    foreach pin [get_pins -quiet -of_objects $cell] {
      puts $fp " PIN $pin [get_property DIRECTION $pin] NET [get_nets -quiet -of_objects $pin] CLOCKS [get_clocks -quiet -of_objects $pin]"
    }
  }
}
close $fp
report_property [get_ports tx_clk_out_p] -file tx-clock-port.rpt
report_clocks -file baseline-clocks.rpt
check_timing -verbose -file baseline-check-timing.rpt
close_design
exit
