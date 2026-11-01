`timescale 1ns/1ps
// Property test for the vendor divider only. This does not certify RGB mapping,
// panel timings, IO timing, or LVDS serialization on real hardware.
module tb_display_half_clock;
  reg pclk = 0;
  reg rst_n = 1;
  wire divided;
  wire [55:0] unused_data;
  integer input_cycles = 0;
  integer period_checks = 0;
  integer reset_checks = 0;
  realtime previous_rise = 0;
  bit have_rise = 0;

  always #5 pclk = ~pclk;
  dual_pixel_24bpp_lvds_mapping dut(
    .pclk_in(pclk), .vid_hsync(1'b0), .vid_vsync(1'b0),
    .vid_data_enable(1'b1), .vid_data_in(24'h963ac5),
    .reset_in_n(rst_n), .pclk_out(divided), .data_out(unused_data));

  always @(posedge pclk) begin
    if (rst_n) input_cycles = input_cycles + 1;
    #0.002;
    if (!rst_n && divided !== 1'b0) $fatal(1, "clock not held low in reset");
  end
  always @(posedge divided) begin
    if (!rst_n) $fatal(1, "output rise while reset asserted");
    if (have_rise) begin
      if (($realtime-previous_rise < 19.999) || ($realtime-previous_rise > 20.001))
        $fatal(1, "output period is not exactly twice the 10ns input period");
      period_checks = period_checks + 1;
    end
    previous_rise = $realtime;
    have_rise = 1;
  end
  always @(negedge rst_n) begin
    have_rise = 0;
    #0.002;
    if (divided !== 1'b0) $fatal(1, "asynchronous reset did not clear output");
    reset_checks = reset_checks + 1;
  end

  initial begin
    #1 rst_n = 0;
    #16 rst_n = 1;
    repeat (24) @(negedge pclk);
    #2 rst_n = 0;    // Reset while the source clock is low.
    #17 rst_n = 1;
    repeat (25) @(negedge pclk);
    #6 rst_n = 0;    // Reset while the source clock is high.
    #13 rst_n = 1;
    repeat (27) @(negedge pclk);
    #1;
    if (period_checks < 30 || reset_checks != 3 || input_cycles < 70)
      $fatal(1, "insufficient coverage");
    $display("P29_DISPLAY_CLOCK_TB_PASS periods=%0d resets=%0d active_input_cycles=%0d", period_checks, reset_checks, input_cycles);
    $finish;
  end
  initial begin
    #2000 $fatal(1, "timeout");
  end
endmodule
