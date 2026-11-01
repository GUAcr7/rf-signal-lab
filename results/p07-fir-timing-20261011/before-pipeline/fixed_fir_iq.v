// Standalone P07 reference FIR. Not connected to the AD9361/DMA baseline.
// Signed 12-bit I/Q counts, signed 18-bit Q17 coefficients, exact signed
// 36-bit accumulators, ties-to-even rounding, saturated 16-bit output.
// Accepts one input every N_TAPS+2 clocks when downstream is always ready.
// The upstream source MUST honor s_ready; an ADC requires separate buffering.
`timescale 1ns/1ps
module fixed_fir_iq #(
    parameter integer N_TAPS = 63,
    parameter COEFF_FILE = "fpga/ip/fir63_q17.hex"
) (
    input wire clk,
    input wire rst_n,
    input wire signed [11:0] s_i,
    input wire signed [11:0] s_q,
    input wire s_valid,
    output wire s_ready,
    output reg signed [15:0] m_i,
    output reg signed [15:0] m_q,
    output reg m_sat_i,
    output reg m_sat_q,
    output reg m_valid,
    input wire m_ready
);
    localparam [1:0] IDLE = 2'd0, MAC = 2'd1, OUTPUT = 2'd2;
    reg [1:0] state;
    reg [5:0] tap_index;
    reg signed [17:0] coefficients [0:N_TAPS-1];
    reg signed [11:0] history_i [0:N_TAPS-1];
    reg signed [11:0] history_q [0:N_TAPS-1];
    reg signed [35:0] accumulator_i, accumulator_q;
    wire signed [29:0] product_i = history_i[tap_index] * coefficients[tap_index];
    wire signed [29:0] product_q = history_q[tap_index] * coefficients[tap_index];
    wire signed [35:0] next_i = accumulator_i + {{6{product_i[29]}}, product_i};
    wire signed [35:0] next_q = accumulator_q + {{6{product_q[29]}}, product_q};
    wire [16:0] converted_i = round_and_saturate(next_i);
    wire [16:0] converted_q = round_and_saturate(next_q);
    integer k;

    assign s_ready = (state == IDLE) && rst_n;

    // Return {saturated, signed_count[15:0]}. Widen before negating so
    // the most-negative accumulator is also well-defined.
    function [16:0] round_and_saturate;
        input signed [35:0] value;
        reg signed [36:0] extended;
        reg [36:0] magnitude;
        reg [19:0] quotient;
        reg [16:0] remainder;
        reg signed [20:0] rounded;
        begin
            extended = {value[35], value};
            magnitude = value[35] ? -extended : extended;
            quotient = magnitude >> 17;
            remainder = magnitude[16:0];
            if ((remainder > 17'd65536) ||
                ((remainder == 17'd65536) && quotient[0]))
                quotient = quotient + 1'b1;
            rounded = $signed({1'b0, quotient});
            if (value[35]) rounded = -rounded;
            if (rounded > 21'sd32767)
                round_and_saturate = {1'b1, 16'h7fff};
            else if (rounded < -21'sd32768)
                round_and_saturate = {1'b1, 16'h8000};
            else
                round_and_saturate = {1'b0, rounded[15:0]};
        end
    endfunction

    initial begin
        for (k = 0; k < N_TAPS; k = k + 1) coefficients[k] = 0;
        if (COEFF_FILE != "") $readmemh(COEFF_FILE, coefficients);
`ifndef SYNTHESIS
        if ((N_TAPS < 1) || (N_TAPS > 63))
            $fatal(1, "N_TAPS must be in [1,63]");
`endif
    end

    always @(posedge clk) begin
        if (!rst_n) begin
            state <= IDLE;
            tap_index <= 0;
            accumulator_i <= 0;
            accumulator_q <= 0;
            m_i <= 0;
            m_q <= 0;
            m_sat_i <= 0;
            m_sat_q <= 0;
            m_valid <= 0;
            for (k = 0; k < N_TAPS; k = k + 1) begin
                history_i[k] <= 0;
                history_q[k] <= 0;
            end
        end else begin
            case (state)
                IDLE: begin
                    if (s_valid && s_ready) begin
                        for (k = N_TAPS-1; k > 0; k = k - 1) begin
                            history_i[k] <= history_i[k-1];
                            history_q[k] <= history_q[k-1];
                        end
                        history_i[0] <= s_i;
                        history_q[0] <= s_q;
                        accumulator_i <= 0;
                        accumulator_q <= 0;
                        tap_index <= 0;
                        state <= MAC;
                    end
                end
                MAC: begin
                    if (tap_index == N_TAPS-1) begin
                        m_i <= converted_i[15:0];
                        m_q <= converted_q[15:0];
                        m_sat_i <= converted_i[16];
                        m_sat_q <= converted_q[16];
                        m_valid <= 1;
                        state <= OUTPUT;
                    end else begin
                        accumulator_i <= next_i;
                        accumulator_q <= next_q;
                        tap_index <= tap_index + 1'b1;
                    end
                end
                OUTPUT: begin
                    if (m_valid && m_ready) begin
                        m_valid <= 0;
                        state <= IDLE;
                    end
                end
                default: begin
                    state <= IDLE;
                    m_valid <= 0;
                end
            endcase
        end
    end
endmodule
