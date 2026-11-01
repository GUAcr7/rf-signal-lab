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

# hdmi out vs hs de pclk

# hdmi out blue

# hdmi out green

# hdmi out red


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
