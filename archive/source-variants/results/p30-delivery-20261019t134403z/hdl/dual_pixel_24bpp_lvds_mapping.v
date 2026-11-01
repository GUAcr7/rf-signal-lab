
/**
 * Copyright (C) 2013 Guangzhou Tronlong Electronic Technology Co., Ltd. - www.tronlong.com
 *
 * @file dual_pixel_24bpp_lvds_mapping.v
 *
 * @brief 	The RGB data (color depth of 8bit) and line field synchronization signal are 
 *			arranged according to LVDS video standard format, and then output parallel data.
 *
 * @author Tronlong <support@tronlong.com>
 *
 * @version V1.0
 *
 * @date 2020-10-14
 *
 **/
`timescale 1ps/1ps

module dual_pixel_24bpp_lvds_mapping (
    input			pclk_in,			// pixel clock input
    (* X_INTERFACE_IGNORE = "true" *)
    input			vid_hsync,			// line synchronization signal
    (* X_INTERFACE_IGNORE = "true" *)
    input			vid_vsync,			// frame synchronization signal
    (* X_INTERFACE_IGNORE = "true" *)
    input 			vid_data_enable,	// data enable
    (* X_INTERFACE_IGNORE = "true" *)
    input   [23:0]	vid_data_in,		// pixel data
	
	input			reset_in_n,			// reset (active low)
	
	output			pclk_out,			// pixel rate frequency generator clock (pclk_in / 2 )
    (* X_INTERFACE_IGNORE = "true" *)
	output	[55:0]	data_out			// dual pixel data output (dual Pixel/24bpp LVDS Mapping)
);

wire			pixel_clk;				// Before pclk_out passes through BUFG
wire	[27:0]	pixel_data_remap;		// Single Pixel/24bpp LVDS Mapping
reg		[27:0]	odd_pixel_data;			// Odd pixel data
reg		[27:0]	even_pixel_data;		// Even pixel data
reg				parity_flag;			// Assign values to even and odd pixels according to this flag


/* RGB data */
wire	[7:0]   pixel_data_r;
wire   	[7:0]   pixel_data_g;
wire    [7:0]  	pixel_data_b;

/* Get RGB data */
assign pixel_data_r = vid_data_in[23:16];
assign pixel_data_g = vid_data_in[15:8];
assign pixel_data_b = vid_data_in[7:0];

/* Single Pixel/24bpp LVDS Mapping (VESA format standard) */
assign pixel_data_remap = {{pixel_data_r[6], pixel_data_r[7], pixel_data_g[6], pixel_data_g[7], pixel_data_b[6], pixel_data_b[7], 1'b0},             //  ch3
						   {pixel_data_b[2], pixel_data_b[3], pixel_data_b[4], pixel_data_b[5], vid_hsync, vid_vsync, vid_data_enable},   			 //  ch2
						   {pixel_data_g[1], pixel_data_g[2], pixel_data_g[3], pixel_data_g[4], pixel_data_g[5], pixel_data_b[0], pixel_data_b[1]},  //  ch1
						   {pixel_data_r[0], pixel_data_r[1], pixel_data_r[2], pixel_data_r[3], pixel_data_r[4], pixel_data_r[5], pixel_data_g[0]}}; //  ch0

// {{{ Get even and odd pixel data  ---------------------------
always @ (posedge pclk_in or negedge reset_in_n)
	begin
		if(!reset_in_n)
			parity_flag <= 1'b0;
		else 
			parity_flag <= ~parity_flag;
	end

always @ (posedge pclk_in or negedge reset_in_n)
	begin
		if(!reset_in_n)
			begin
				odd_pixel_data <= 28'd0;
				even_pixel_data <= 28'd0;
			end
		else if(parity_flag)
			odd_pixel_data <= pixel_data_remap;
		else
			even_pixel_data <= pixel_data_remap;
	end	
// }}} Get even and odd pixel data ---------------------------

/* Combining odd pixel data and even data into dual pixel data */
assign data_out = {even_pixel_data, odd_pixel_data};

// {{{ pixel rate frequency generator clock  ---------------------------
assign pixel_clk = parity_flag ? 1'b1 : 1'b0;

BUFG bufg_pclk_out (
	.I	(pixel_clk), 
	.O	(pclk_out)
) ;
// }}} pixel rate frequency generator clock ---------------------------

endmodule
