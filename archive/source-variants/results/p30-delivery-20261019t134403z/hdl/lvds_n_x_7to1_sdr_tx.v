/**
 * Copyright (C) 2013 Guangzhou Tronlong Electronic Technology Co., Ltd. - www.tronlong.com
 *
 * @file lvds_n_x_7to1_sdr_tx.v
 *
 * @brief lvds tx sdr mode.
 *
 * @author Tronlong <support@tronlong.com>
 *
 * @version V1.0
 *
 * @date 2020-10-14
 *
 **/
`timescale 1ps/1ps

module lvds_n_x_7to1_sdr_tx #(
	/* Parameters */
	parameter integer	D = 4,					// Set the number of outputs per channel to be 4 in this example.
	parameter integer	N = 2					// Set the number of channels to be 2 in this example.
)(
	input					reset_in_n,			// reset (active low)	
	input					clk_in,				// pixel rate frequency generator clock input
    (* X_INTERFACE_IGNORE = "true" *)
	input	[D*N*7-1:0]		data_in,			// pixel data
	
    (* X_INTERFACE_IGNORE = "true" *)
	output	[N-1:0]			clk_out_p,  		// lvds channel clock output
    (* X_INTERFACE_IGNORE = "true" *)
	output	[N-1:0]			clk_out_n,
	
    (* X_INTERFACE_IGNORE = "true" *)
	output	[D*N-1:0]		data_out_p, 		// lvds channel data outputs
    (* X_INTERFACE_IGNORE = "true" *)
	output	[D*N-1:0]		data_out_n
);	

localparam 	[6:0] 	TX_CLK_GEN   = 7'b1100011;	// Transmit a constant to make a 4:3 clock, two ticks in advance of bit0 of the data word. OR make a 3:4 clock (7'b1100001).

wire				pixel_clk;					// pixel clock	
wire				txclk;						// lvds tx clock 
wire				tx_mmcm_lckd;

/* Clock Input */
clock_generator_pll_7_to_1_diff_sdr #(
	.DIFF_TERM		("TRUE"),		// Parameter to enable internal differential termination
	.PIXEL_CLOCK	("BUF_G"),		// Parameter to set pixel clock buffer type, BUFIO, BUF_H, BUF_G
	.TX_CLOCK		("BUF_G"),		// Parameter to set TX clock buffer type, BUFIO, BUF_H, BUF_G
	.USE_PLL		("TRUE"),		// Parameter to enable PLL 
	.MMCM_MODE		(2),			// Parameter to set multiplier for MMCM to get VCO in correct operating range. 1 multiplies input clock by 7, 2 multiplies clock by 14, etc
	.CLKIN_PERIOD 	(13.468)		// Set input clock period, period = 1 / 74.25MHz
) clkgen (                               
	.reset			(~reset_in_n),	// Reset
	.clkin_p		(clk_in),		// pixel rate frequency generator clock input
	.clkin_n		(1'b0),
	.txclk			(txclk),		// lvds tx clock 
	.pixel_clk		(pixel_clk),	// pixel clock 
	.status			(),
	.mmcm_lckd		(tx_mmcm_lckd)
);

/* Transmitter Logic for N D-bit channels */
n_x_serdes_7_to_1_diff_sdr #(
	.D				(D),			// Set the number of outputs per channel to be 4
    .N				(N),			// 2 channels
	.DATA_FORMAT 	("PER_CHANL")	// PER_CLOCK or PER_CHANL data formatting
) dataout (                              
	.dataout_p  	(data_out_p),	// lvds channel data outputs
	.dataout_n  	(data_out_n),	// lvds channel data outputs
	.clkout_p  		(clk_out_p),	// lvds channel clock output
	.clkout_n  		(clk_out_n),	// lvds channel clock output
	.txclk    		(txclk),		// lvds tx clock 
	.pixel_clk    	(pixel_clk),	// pixel clock
	.reset   		(~tx_mmcm_lckd),
	.clk_pattern  	(TX_CLK_GEN),	// Transmit a constant to make the clock
	.datain  		(data_in)		// pixel data
);

endmodule
