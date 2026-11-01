`timescale 1ns/1ps
// Combinational carrier mapping. Keep Linux EMIO numbers stable:
// touch=0, AD9361 status/control/reset=32..46, enable/txnrx=47..48.
// Unused PS inputs are tied low; PS direction/output bits remain independent.
module rf_display_gpio (
    input wire [63:0] ps_o,
    input wire [63:0] ps_t,
    input wire [14:0] rf_i,
    input wire touch_intr,
    output wire [63:0] ps_i,
    output wire [14:0] rf_o,
    output wire [14:0] rf_t,
    output wire up_enable,
    output wire up_txnrx
);
    assign ps_i = {17'b0, rf_i, 31'b0, touch_intr};
    assign rf_o = ps_o[46:32];
    assign rf_t = ps_t[46:32];
    assign up_enable = ps_o[47];
    assign up_txnrx = ps_o[48];
endmodule
