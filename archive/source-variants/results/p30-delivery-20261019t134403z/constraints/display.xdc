# LCD screen interface
set_property -dict {PACKAGE_PIN R27 IOSTANDARD LVCMOS33} [get_ports lcd_pclk]
set_property -dict {PACKAGE_PIN AC21 IOSTANDARD LVCMOS25 IOB TRUE} [get_ports lcd_vsync]
set_property -dict {PACKAGE_PIN W23 IOSTANDARD LVCMOS25 IOB TRUE} [get_ports lcd_hsync]
set_property -dict {PACKAGE_PIN P26 IOSTANDARD LVCMOS33 IOB TRUE} [get_ports lcd_de]
set_property -dict {PACKAGE_PIN K16 IOSTANDARD LVCMOS18} [get_ports lcd_pwm_backlight]

set_property -dict {PACKAGE_PIN U29 IOSTANDARD LVCMOS33 IOB TRUE} [get_ports {lcd_data_r[0]}]
set_property -dict {PACKAGE_PIN T27 IOSTANDARD LVCMOS33 IOB TRUE} [get_ports {lcd_data_r[1]}]
set_property -dict {PACKAGE_PIN V23 IOSTANDARD LVCMOS33 IOB TRUE} [get_ports {lcd_data_r[2]}]
set_property -dict {PACKAGE_PIN W24 IOSTANDARD LVCMOS33 IOB TRUE} [get_ports {lcd_data_r[3]}]
set_property -dict {PACKAGE_PIN P25 IOSTANDARD LVCMOS33 IOB TRUE} [get_ports {lcd_data_r[4]}]

set_property -dict {PACKAGE_PIN R21 IOSTANDARD LVCMOS33 IOB TRUE} [get_ports {lcd_data_g[0]}]
set_property -dict {PACKAGE_PIN N27 IOSTANDARD LVCMOS33 IOB TRUE} [get_ports {lcd_data_g[1]}]
set_property -dict {PACKAGE_PIN N26 IOSTANDARD LVCMOS33 IOB TRUE} [get_ports {lcd_data_g[2]}]
set_property -dict {PACKAGE_PIN N28 IOSTANDARD LVCMOS33 IOB TRUE} [get_ports {lcd_data_g[3]}]
set_property -dict {PACKAGE_PIN P28 IOSTANDARD LVCMOS33 IOB TRUE} [get_ports {lcd_data_g[4]}]
set_property -dict {PACKAGE_PIN T29 IOSTANDARD LVCMOS33 IOB TRUE} [get_ports {lcd_data_g[5]}]

set_property -dict {PACKAGE_PIN W28 IOSTANDARD LVCMOS33 IOB TRUE} [get_ports {lcd_data_b[0]}]
set_property -dict {PACKAGE_PIN V27 IOSTANDARD LVCMOS33 IOB TRUE} [get_ports {lcd_data_b[1]}]
set_property -dict {PACKAGE_PIN P23 IOSTANDARD LVCMOS33 IOB TRUE} [get_ports {lcd_data_b[2]}]
set_property -dict {PACKAGE_PIN P24 IOSTANDARD LVCMOS33 IOB TRUE} [get_ports {lcd_data_b[3]}]
set_property -dict {PACKAGE_PIN P21 IOSTANDARD LVCMOS33 IOB TRUE} [get_ports {lcd_data_b[4]}]

# lvds screen interface
set_property PACKAGE_PIN AH23 [get_ports {lvds_data_out_p[7]}]
set_property PACKAGE_PIN AJ23 [get_ports {lvds_data_out_p[6]}]
set_property PACKAGE_PIN AA24 [get_ports {lvds_data_out_p[5]}]
set_property PACKAGE_PIN Y22 [get_ports {lvds_data_out_p[4]}]
set_property PACKAGE_PIN AD21 [get_ports {lvds_data_out_p[3]}]
set_property PACKAGE_PIN AA22 [get_ports {lvds_data_out_p[2]}]
set_property PACKAGE_PIN AB21 [get_ports {lvds_data_out_p[1]}]
set_property PACKAGE_PIN W21 [get_ports {lvds_data_out_p[0]}]
set_property PACKAGE_PIN AD23 [get_ports {lvds_clk_out_p[1]}]
set_property PACKAGE_PIN AE22 [get_ports {lvds_clk_out_p[0]}]
set_property IOSTANDARD LVDS_25 [get_ports lvds_clk_out_p*]
set_property IOSTANDARD LVDS_25 [get_ports lvds_data_out_p*]

# hdmi out vs hs de pclk
set_property PACKAGE_PIN R25 [get_ports o_video_pclk]
set_property PACKAGE_PIN R26 [get_ports o_video_vsync]
set_property PACKAGE_PIN Y25 [get_ports o_video_hsync]
set_property PACKAGE_PIN AA25 [get_ports o_video_de]

# hdmi out blue
set_property PACKAGE_PIN V24 [get_ports {o_video_data[0]}]
set_property PACKAGE_PIN U24 [get_ports {o_video_data[1]}]
set_property PACKAGE_PIN U27 [get_ports {o_video_data[2]}]
set_property PACKAGE_PIN P30 [get_ports {o_video_data[3]}]
set_property PACKAGE_PIN R30 [get_ports {o_video_data[4]}]
set_property PACKAGE_PIN U21 [get_ports {o_video_data[5]}]
set_property PACKAGE_PIN V21 [get_ports {o_video_data[6]}]
set_property PACKAGE_PIN U22 [get_ports {o_video_data[7]}]

# hdmi out green
set_property PACKAGE_PIN U26 [get_ports {o_video_data[8]}]
set_property PACKAGE_PIN W30 [get_ports {o_video_data[9]}]
set_property PACKAGE_PIN V22 [get_ports {o_video_data[10]}]
set_property PACKAGE_PIN V28 [get_ports {o_video_data[11]}]
set_property PACKAGE_PIN V29 [get_ports {o_video_data[12]}]
set_property PACKAGE_PIN T25 [get_ports {o_video_data[13]}]
set_property PACKAGE_PIN T24 [get_ports {o_video_data[14]}]
set_property PACKAGE_PIN R22 [get_ports {o_video_data[15]}]

# hdmi out red
set_property PACKAGE_PIN W29 [get_ports {o_video_data[16]}]
set_property PACKAGE_PIN P29 [get_ports {o_video_data[17]}]
set_property PACKAGE_PIN N29 [get_ports {o_video_data[18]}]
set_property PACKAGE_PIN R23 [get_ports {o_video_data[19]}]
set_property PACKAGE_PIN U25 [get_ports {o_video_data[20]}]
set_property PACKAGE_PIN V26 [get_ports {o_video_data[21]}]
set_property PACKAGE_PIN T22 [get_ports {o_video_data[22]}]
set_property PACKAGE_PIN T23 [get_ports {o_video_data[23]}]

set_property IOSTANDARD LVCMOS33 [get_ports {o_video*}]

# XPT2046(ads7846 touch chip)
set_property PACKAGE_PIN G2 [get_ports SPI0_SS_O]
set_property IOSTANDARD LVCMOS15 [get_ports SPI0_SS_O]
set_property PULLUP true [get_ports SPI0_SS_O]

# XPT2046 interrupt pin
set_property -dict {PACKAGE_PIN C6 IOSTANDARD LVCMOS15} [get_ports touch_intr]

# spi0 interface
set_property -dict {PACKAGE_PIN K8 IOSTANDARD LVCMOS15} [get_ports SPI0_MISO_I]
set_property -dict {PACKAGE_PIN L8 IOSTANDARD LVCMOS15} [get_ports SPI0_MOSI_O]
set_property -dict {PACKAGE_PIN F5 IOSTANDARD LVCMOS15} [get_ports SPI0_SCLK_O]

# Enable BitStream Compression
set_property BITSTREAM.GENERAL.COMPRESS true [current_design]
