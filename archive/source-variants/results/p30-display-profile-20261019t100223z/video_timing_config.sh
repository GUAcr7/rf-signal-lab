# video timing configuration
if [ $1 -eq 1 ]
then
	echo "Select video timing 1920x1080"
	# Pixel clock (148.5Mhz) configuration
	# VCO = VCO Frequency = (Input Clock Frequency) * (CLKFBOUT_MULT) / DIVCLK_DIVIDE = 100MHz * 37.125 / 4 = 928.125MHz
	devmem 0x43c10208 w 0xFA06		# CLKOUT0_DIVCLK_DIVIDE = VCO / CLKOUT0 = 928.125MHz /148.5MHz = 6.250
	devmem 0x43c1020C w 0x0
	
	sleep 1s						# Wait for clock configuration to complete
	devmem 0x43c1025C w 0x3			# Initiate reconfiguration

	# Configure VTC IP core
	devmem 0x43C20000 w 0x80000000	# reset vtc
	devmem 0x43C20000 w 0x2			# enable register update

	devmem 0x43C20000 w 0			# disable register update

	devmem 0x43C20070 w 0x898		# htotal = 2200
	devmem 0x43C20074 w 0x4650465	# vtotal | vtotal << 16 = 1125 | 1125 << 16
	devmem 0x43C20060 w 0x4380780	# hactive | vactive << 16 = 1920 | 1080 << 16	
	devmem 0x43C20078 w 0x80407D8	# hsync_start | hsync_end << 16 = 2008 | 2052 << 16
	devmem 0x43C20080 w 0x440043B	# vsync_start | vsync_end << 16 = 1083 | 1088 << 16
	
	devmem 0x43C2007c w 0x7800780	# vblank_start | vblank_end << 16 = 1920 | 1920 <<16
	devmem 0x43C20084 w 0x7800780	# vsync_start | vsync_end << 16 = 1920 | 1920 <<16

	devmem 0x43C20000 w 0x7EF06		# configure source & enable register update & enable vtc
fi

if [ $1 -eq 2 ]
then
	echo "Select video timing 800x480"
	# Pixel clock (33Mhz) configuration
	# VCO = VCO Frequency = (Input Clock Frequency) * (CLKFBOUT_MULT) / DIVCLK_DIVIDE = 100MHz * 37.125 / 4 = 928.125MHz
	devmem 0x43c10208 w 0x7D1C		# CLKOUT0_DIVCLK_DIVIDE = VCO / CLKOUT0 = 928.125MHz / 33MHz = 37.125
	devmem 0x43c1020C w 0x0
	
	sleep 1s						# Wait for clock configuration to complete
	devmem 0x43c1025C w 0x3			# Initiate reconfiguration

	# Configure VTC IP core
	devmem 0x43C20000 w 0x80000000	# reset vtc
	devmem 0x43C20000 w 0x2			# enable register update

	devmem 0x43C20000 w 0			# disable register update

	devmem 0x43C20070 w 0x420		# htotal = 1056
	devmem 0x43C20074 w 0x2100210	# vtotal | vtotal << 16 = 528 | 528 << 16
	devmem 0x43C20060 w 0x1E00320	# hactive | vactive << 16 = 800 | 480 << 16	
	devmem 0x43C20078 w 0x3C80348	# hsync_start | hsync_end << 16 = 840 | 968 << 16
	devmem 0x43C20080 w 0x1E401E0	# vsync_start | vsync_end << 16 = 480 | 484 << 16
	
	devmem 0x43C2007c w 0x3200320	# vblank_start | vblank_end << 16 = 800 | 800 <<16
	devmem 0x43C20084 w 0x3200320	# vsync_start | vsync_end << 16 = 800 | 800 <<16

	devmem 0x43C20000 w 0x7EF06		# configure source & enable register update & enable vtc
fi
