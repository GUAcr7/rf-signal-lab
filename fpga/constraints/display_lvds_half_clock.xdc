# The vendor FF toggles on every input rising edge. This file is declarative:
# XDC does not support Tcl if/unset control flow. Check hierarchy uniqueness and
# the resulting clock period in the build Tcl after opening the synthesized run.
# Do not replace these paths with a false path or change the source period.
create_generated_clock -name p29_lvds_half_pclk -source [get_pins -hier -filter {NAME =~ */dual_pixel_24bpp_lvds_mapping_0/inst/parity_flag_reg/C}] -divide_by 2 [get_pins -hier -filter {NAME =~ */dual_pixel_24bpp_lvds_mapping_0/inst/parity_flag_reg/Q}]
