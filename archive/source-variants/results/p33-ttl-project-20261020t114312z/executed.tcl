set_param general.maxThreads 2
open_project {E:/p33-ttl-114312/project/combined.xpr}
if {[get_property PART [current_project]] ne "xc7z100ffg900-2"} {error "wrong device"}
open_bd_design [get_files */system.bd]
foreach name {dual_pixel_24bpp_lvds_mapping_0 lvds_n_x_7to1_sdr_tx_0} {
  set obj [get_bd_cells -quiet $name]
  if {[llength $obj] != 1} {error "missing unused branch $name"}
  delete_bd_objs $obj
}
foreach name {lvds_clk_out_n lvds_clk_out_p lvds_data_out_n lvds_data_out_p o_video_data o_video_de o_video_hsync o_video_pclk o_video_vsync} {
  set obj [get_bd_ports -quiet $name]
  if {[llength $obj] != 1} {error "missing removed port $name"}
  delete_bd_objs $obj
}
set_property CONFIG.CLKOUT1_REQUESTED_OUT_FREQ {33.000} [get_bd_cells clk_wiz_0]
set half [get_files -quiet */half_clock.xdc]
if {[llength $half] != 1} {error "half-clock XDC ambiguous"}
remove_files $half
validate_bd_design
save_bd_design
write_bd_tcl -force {E:/p33-ttl-114312/p33-ttl-validated.tcl}
puts "P33_TTL_BD_VALIDATED no_synthesis_no_bitstream"
close_project
exit 0
