open_checkpoint E:/p30c-1019-174235/merged-route.dcp
set pll [get_cells -hier -filter {NAME =~ */lvds_n_x_7to1_sdr_tx_0/inst/clkgen/tx_mmcme2_adv_inst}]
if {[llength $pll] != 1} {error "PLL lookup not unique"}
report_property $pll -file lvds-pll-properties.rpt
# Diagnostic runtime model only: override upstream pixel output at 33MHz in memory.
# This deliberately cuts the upstream MMCM relation; it is NOT deployable XDC.
set pixel [get_pins -hier -filter {NAME =~ */clk_wiz_0/inst/CLK_CORE_DRP_I/clk_inst/mmcm_adv_inst/CLKOUT0}]
if {[llength $pixel] != 1} {error "Pixel lookup not unique"}
create_clock -name p33_runtime_pixel_probe -period 30.303030 $pixel
set_property CLKIN1_PERIOD 60.606 $pll
report_clocks -file runtime-explicit-period-clocks.rpt
report_drc -file runtime-explicit-period-drc.rpt
close_design
exit

