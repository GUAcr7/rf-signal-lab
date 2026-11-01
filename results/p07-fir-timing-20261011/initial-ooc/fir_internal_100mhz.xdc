# Standalone synthesis estimate: only the internal clock is modeled.
# No input/output delay, board clock, pin, drive, load or ADC/DMA assumption.
# rst_n is synchronous in the RTL. Do not false-path it or the handshake ports.
create_clock -name fir_clk -period 10.000 [get_ports clk]
