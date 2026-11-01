// ***************************************************************************
// ***************************************************************************
// Copyright 2014 - 2017 (c) Analog Devices, Inc. All rights reserved.
//
// In this HDL repository, there are many different and unique modules, consisting
// of various HDL (Verilog or VHDL) components. The individual modules are
// developed independently, and may be accompanied by separate and unique license
// terms.
//
// The user should read each of these license terms, and understand the
// freedoms and responsabilities that he or she has by using this source/core.
//
// This core is distributed in the hope that it will be useful, but WITHOUT ANY
// WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
// A PARTICULAR PURPOSE.
//
// Redistribution and use of source or resulting binaries, with or without modification
// of this file, are permitted under one of the following two license terms:
//
//   1. The GNU General Public License version 2 as published by the
//      Free Software Foundation, which can be found in the top level directory
//      of this repository (LICENSE_GPL2), and also online at:
//      <https://www.gnu.org/licenses/old-licenses/gpl-2.0.html>
//
// OR
//
//   2. An ADI specific BSD license, which can be found in the top level directory
//      of this repository (LICENSE_ADIBSD), and also on-line at:
//      https://github.com/analogdevicesinc/hdl/blob/master/LICENSE_ADIBSD
//      This will allow to generate bit files and not release the source code,
//      as long as it attaches to an ADI device.
//
// ***************************************************************************
// ***************************************************************************

`timescale 1ns/100ps

module rf_display_top (

  inout       [14:0]      ddr_addr,
  inout       [ 2:0]      ddr_ba,
  inout                   ddr_cas_n,
  inout                   ddr_ck_n,
  inout                   ddr_ck_p,
  inout                   ddr_cke,
  inout                   ddr_cs_n,
  inout       [ 3:0]      ddr_dm,
  inout       [31:0]      ddr_dq,
  inout       [ 3:0]      ddr_dqs_n,
  inout       [ 3:0]      ddr_dqs_p,
  inout                   ddr_odt,
  inout                   ddr_ras_n,
  inout                   ddr_reset_n,
  inout                   ddr_we_n,

  inout                   fixed_io_ddr_vrn,
  inout                   fixed_io_ddr_vrp,
  inout       [53:0]      fixed_io_mio,
  inout                   fixed_io_ps_clk,
  inout                   fixed_io_ps_porb,
  inout                   fixed_io_ps_srstb,



  input wire SPI0_MISO_I,
  output wire SPI0_MOSI_O,
  output wire SPI0_SCLK_O,
  output wire SPI0_SS_O,
  output wire [4:0] lcd_data_b,
  output wire [5:0] lcd_data_g,
  output wire [4:0] lcd_data_r,
  output wire lcd_de,
  output wire lcd_hsync,
  output wire lcd_pclk,
  output wire lcd_pwm_backlight,
  output wire lcd_vsync,
  output wire [1:0] lvds_clk_out_n,
  output wire [1:0] lvds_clk_out_p,
  output wire [7:0] lvds_data_out_n,
  output wire [7:0] lvds_data_out_p,
  output wire [23:0] o_video_data,
  output wire o_video_de,
  output wire o_video_hsync,
  output wire o_video_pclk,
  output wire o_video_vsync,
  input wire touch_intr,
  input                   rx_clk_in_p,
  input                   rx_clk_in_n,
  input                   rx_frame_in_p,
  input                   rx_frame_in_n,
  input       [ 5:0]      rx_data_in_p,
  input       [ 5:0]      rx_data_in_n,
  output                  tx_clk_out_p,
  output                  tx_clk_out_n,
  output                  tx_frame_out_p,
  output                  tx_frame_out_n,
  output      [ 5:0]      tx_data_out_p,
  output      [ 5:0]      tx_data_out_n,

  output                  enable,
  output                  txnrx,



  inout                   gpio_resetb,
  inout                   gpio_sync,
  inout                   gpio_en_agc,
  inout       [ 3:0]      gpio_ctl,
  inout       [ 7:0]      gpio_status,

  output                  spi_csn,
  output                  spi_clk,
  output                  spi_mosi,
  input                   spi_miso
  );

  // internal signals

  wire    [63:0]  gpio_i;
  wire    [63:0]  gpio_o;
  wire    [63:0]  gpio_t;
  wire            clk;
  wire            dma_dac_dunf;
  wire            core_dac_dunf;
  wire    [63:0]  dma_dac_ddata;
  wire    [63:0]  core_dac_ddata;
  wire            dma_dac_en;
  wire            core_dac_en;
  wire            dma_dac_dvalid;
  wire            core_dac_dvalid;
  wire            dma_adc_ovf;
  wire            core_adc_ovf;
  wire    [63:0]  dma_adc_ddata;
  wire    [63:0]  core_adc_ddata;
  wire            dma_adc_dwr;
  wire            core_adc_dwr;
  wire            dma_adc_dsync;
  wire            core_adc_dsync;
  wire    [31:0]  adc_gpio_input;
  wire    [31:0]  adc_gpio_output;
  wire    [31:0]  dac_gpio_input;
  wire    [31:0]  dac_gpio_output;
  wire            tdd_sync_t;
  wire            tdd_sync_o;
  wire            tdd_sync_i;


  wire [14:0] rf_gpio_i, rf_gpio_o, rf_gpio_t;
  wire mapped_enable, mapped_txnrx;
  rf_display_gpio i_gpio_mapping (
    .ps_o(gpio_o), .ps_t(gpio_t), .rf_i(rf_gpio_i),
    .touch_intr(touch_intr), .ps_i(gpio_i),
    .rf_o(rf_gpio_o), .rf_t(rf_gpio_t),
    .up_enable(mapped_enable), .up_txnrx(mapped_txnrx));
  // No external TDD sync connector is used by this carrier integration.
  assign tdd_sync_i = 1'b0;
  // instantiations

  ad_iobuf #(.DATA_WIDTH(15)) i_iobuf (
    .dio_t (rf_gpio_t),
    .dio_i (rf_gpio_o),
    .dio_o (rf_gpio_i),
    .dio_p ({gpio_resetb,        // 46:46
             gpio_sync,          // 45:45
             gpio_en_agc,        // 44:44
             gpio_ctl,           // 43:40
             gpio_status}));     // 39:32
             

               
  system i_system_wrapper (
    .SPI0_MISO_I (SPI0_MISO_I),
    .SPI0_MOSI_O (SPI0_MOSI_O),
    .SPI0_SCLK_O (SPI0_SCLK_O),
    .SPI0_SS_O (SPI0_SS_O),
    .lcd_data_b (lcd_data_b),
    .lcd_data_g (lcd_data_g),
    .lcd_data_r (lcd_data_r),
    .lcd_de (lcd_de),
    .lcd_hsync (lcd_hsync),
    .lcd_pclk (lcd_pclk),
    .lcd_pwm_backlight (lcd_pwm_backlight),
    .lcd_vsync (lcd_vsync),
    .lvds_clk_out_n (lvds_clk_out_n),
    .lvds_clk_out_p (lvds_clk_out_p),
    .lvds_data_out_n (lvds_data_out_n),
    .lvds_data_out_p (lvds_data_out_p),
    .o_video_data (o_video_data),
    .o_video_de (o_video_de),
    .o_video_hsync (o_video_hsync),
    .o_video_pclk (o_video_pclk),
    .o_video_vsync (o_video_vsync),
    .ddr_addr (ddr_addr),
    .ddr_ba (ddr_ba),
    .ddr_cas_n (ddr_cas_n),
    .ddr_ck_n (ddr_ck_n),
    .ddr_ck_p (ddr_ck_p),
    .ddr_cke (ddr_cke),
    .ddr_cs_n (ddr_cs_n),
    .ddr_dm (ddr_dm),
    .ddr_dq (ddr_dq),
    .ddr_dqs_n (ddr_dqs_n),
    .ddr_dqs_p (ddr_dqs_p),
    .ddr_odt (ddr_odt),
    .ddr_ras_n (ddr_ras_n),
    .ddr_reset_n (ddr_reset_n),
    .ddr_we_n (ddr_we_n),
    .enable (enable),
    .fixed_io_ddr_vrn (fixed_io_ddr_vrn),
    .fixed_io_ddr_vrp (fixed_io_ddr_vrp),
    .fixed_io_mio (fixed_io_mio),
    .fixed_io_ps_clk (fixed_io_ps_clk),
    .fixed_io_ps_porb (fixed_io_ps_porb),
    .fixed_io_ps_srstb (fixed_io_ps_srstb),
    .gpio_i (gpio_i),
    .gpio_o (gpio_o),
    .gpio_t (gpio_t),
    .rx_clk_in_n (rx_clk_in_n),
    .rx_clk_in_p (rx_clk_in_p),
    .rx_data_in_n (rx_data_in_n),
    .rx_data_in_p (rx_data_in_p),
    .rx_frame_in_n (rx_frame_in_n),
    .rx_frame_in_p (rx_frame_in_p),
    .spi1_clk_i (1'b0),
    .spi1_clk_o (spi_clk),
    .spi1_csn_0_o (spi_csn),
    .spi1_csn_1_o (),
    .spi1_csn_2_o (),
    .spi1_csn_i (1'b1),
    .spi1_sdi_i (spi_miso),
    .spi1_sdo_i (1'b0),
    .spi1_sdo_o (spi_mosi),
    .tdd_sync_i (tdd_sync_i),
    .tdd_sync_o (tdd_sync_o),
    .tdd_sync_t (tdd_sync_t),
    .tx_clk_out_n (tx_clk_out_n),
    .tx_clk_out_p (tx_clk_out_p),
    .tx_data_out_n (tx_data_out_n),
    .tx_data_out_p (tx_data_out_p),
    .tx_frame_out_n (tx_frame_out_n),
    .tx_frame_out_p (tx_frame_out_p),
    .txnrx (txnrx),
    .up_enable (mapped_enable),
    .up_txnrx (mapped_txnrx));

endmodule

// ***************************************************************************
// ***************************************************************************
