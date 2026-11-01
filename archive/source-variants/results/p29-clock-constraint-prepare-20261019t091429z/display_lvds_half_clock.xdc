# The unchanged vendor parity_flag FF toggles on every rising pclk_in edge.
# Model its /2 clock before the downstream LVDS MMCM/OSERDES timing analysis.
# Do not use a false path, fabricated input clock, or changed source period.
set p29_div_c [get_pins -hier -filter {NAME =~ */dual_pixel_24bpp_lvds_mapping_0/inst/parity_flag_reg/C}]
set p29_div_q [get_pins -hier -filter {NAME =~ */dual_pixel_24bpp_lvds_mapping_0/inst/parity_flag_reg/Q}]
if {[llength $p29_div_c] != 1 || [llength $p29_div_q] != 1} {
    error "P29 vendor clock-divider hierarchy changed; review the netlist"
}
if {[llength [get_clocks -of_objects $p29_div_c]] != 1} {
    error "P29 expected exactly one master pixel clock"
}
create_generated_clock -name p29_lvds_half_pclk -source $p29_div_c -divide_by 2 $p29_div_q
unset p29_div_c
unset p29_div_q
