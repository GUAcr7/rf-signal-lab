`timescale 1ns/1ps
module tb_fixed_fir_iq;
    parameter integer N_TAPS = 63;
    parameter integer RANDOM_STALLS = 1;
    parameter integer USE_DEFAULT_COEFF = 0;
    localparam integer MAX_SAMPLES = 100000;
    reg clk = 0;
    always #5 clk = ~clk;
    reg rst_n = 0;
    reg signed [11:0] s_i = 0, s_q = 0;
    reg s_valid = 0;
    wire s_ready;
    wire signed [15:0] m_i, m_q;
    wire m_sat_i, m_sat_q, m_valid;
    reg m_ready = 0;
    fixed_fir_iq #(.N_TAPS(N_TAPS),
        .COEFF_FILE(USE_DEFAULT_COEFF ? "fpga/ip/fir63_q17.hex" : "")) dut (.*);

    reg [11:0] input_i [0:MAX_SAMPLES-1], input_q [0:MAX_SAMPLES-1];
    reg [15:0] expected_i [0:MAX_SAMPLES-1], expected_q [0:MAX_SAMPLES-1];
    reg expected_sat_i [0:MAX_SAMPLES-1], expected_sat_q [0:MAX_SAMPLES-1];
    reg [4095:0] case_name, path_i, path_q, path_ei, path_eq, path_si, path_sq, path_coeff;
    integer input_count, output_count, sent = 0, received = 0;
    integer cycles = 0, max_cycles, phase = 0, accept_cycle = 0;
    integer stalled_output_cycles = 0, input_wait_cycles = 0;
    integer min_handshake_cycles = 1000000, max_handshake_cycles = 0;
    integer latency;
    integer rounding_checks = 0;
    reg valid_seen = 0, held = 0;
    reg [33:0] held_payload;
    reg accepted_last_edge = 0, source_held = 0;
    reg [23:0] held_input;
    reg [31:0] rng = 32'h735fa329;

    task reset_dut;
        reg pending_before_reset;
        begin
            @(negedge clk);
            pending_before_reset = m_valid;
            rst_n = 0; s_valid = 0; m_ready = 0;
            #1;
            if (pending_before_reset && m_valid !== 1)
                $fatal(1, "sequential output cleared before synchronous reset edge");
            repeat (3) @(posedge clk);
            #1;
            if (m_valid !== 0 || s_ready !== 0)
                $fatal(1, "reset did not clear output/disable input");
            @(negedge clk);
            rst_n = 1;
            #1;
            if (m_valid !== 0 || s_ready !== 1)
                $fatal(1, "ready/valid incorrect after reset");
        end
    endtask

    task check_round;
        input signed [35:0] value;
        input [16:0] expected;
        begin
            if (dut.round_and_saturate(value) !== expected)
                $fatal(1, "independent rounding table mismatch at accumulator=%0d", value);
            rounding_checks = rounding_checks + 1;
        end
    endtask

    // Drive and hold one transaction until it is accepted. Used to make
    // reset arrive in the middle of real work and while an output is blocked.
    task send_probe;
        begin
            @(negedge clk);
            s_i = 12'sd123; s_q = -12'sd177; s_valid = 1;
            do @(posedge clk); while (!s_ready);
            @(negedge clk);
            s_valid = 0;
        end
    endtask

    always @(posedge clk) begin
        cycles = cycles + 1;
        accepted_last_edge = rst_n && (phase == 1) && s_valid && s_ready;
        if (cycles > max_cycles) $fatal(1, "watchdog exceeded at sent=%0d received=%0d", sent, received);
        if (!rst_n) begin
            held = 0;
            source_held = 0;
            valid_seen = 0;
        end else begin
            if (source_held && (s_valid !== 1 || {s_i,s_q} !== held_input))
                $fatal(1, "test source changed a pending input before handshake");
            source_held = s_valid && !s_ready;
            held_input = {s_i,s_q};
            if (held && (m_valid !== 1 || {m_sat_i,m_sat_q,m_i,m_q} !== held_payload))
                $fatal(1, "output changed while backpressured");
            held = m_valid && !m_ready;
            held_payload = {m_sat_i,m_sat_q,m_i,m_q};
            if (phase == 1) begin
                if (s_valid && !s_ready) input_wait_cycles = input_wait_cycles + 1;
                if (s_valid && s_ready) begin
                    if (sent >= output_count) $fatal(1, "extra input accepted");
                    if (!RANDOM_STALLS && sent > 0 && cycles-accept_cycle != N_TAPS+2)
                        $fatal(1, "unstalled input interval is not N_TAPS+2 clocks");
                    sent = sent + 1;
                    accept_cycle = cycles;
                    valid_seen = 0;
                end
                if (m_valid && !valid_seen) begin
                    if (cycles-accept_cycle != N_TAPS+1)
                        $fatal(1, "valid latency mismatch: got=%0d expected=%0d", cycles-accept_cycle, N_TAPS+1);
                    valid_seen = 1;
                end
                if (m_valid && !m_ready) stalled_output_cycles = stalled_output_cycles + 1;
                if (m_valid && m_ready) begin
                    if (received >= output_count || received >= sent)
                        $fatal(1, "unexpected/duplicated output");
                    if (m_i !== expected_i[received] || m_q !== expected_q[received] ||
                        m_sat_i !== expected_sat_i[received] || m_sat_q !== expected_sat_q[received])
                        $fatal(1, "sample %0d differs: got I=%0d Q=%0d sat=%b%b expected I=%0d Q=%0d sat=%b%b",
                            received, $signed(m_i), $signed(m_q), m_sat_i,m_sat_q,
                            $signed(expected_i[received]),$signed(expected_q[received]),
                            expected_sat_i[received],expected_sat_q[received]);
                    latency = cycles-accept_cycle;
                    if (latency < min_handshake_cycles) min_handshake_cycles = latency;
                    if (latency > max_handshake_cycles) max_handshake_cycles = latency;
                    received = received + 1;
                end
            end
        end
    end

    initial begin
        max_cycles = 100000000;
        if (!$value$plusargs("CASE=%s", case_name)) case_name = "unnamed";
        if (!$value$plusargs("INPUT_COUNT=%d", input_count) ||
            !$value$plusargs("OUTPUT_COUNT=%d", output_count) ||
            !$value$plusargs("I=%s", path_i) || !$value$plusargs("Q=%s", path_q) ||
            !$value$plusargs("EI=%s", path_ei) || !$value$plusargs("EQ=%s", path_eq) ||
            !$value$plusargs("SI=%s", path_si) || !$value$plusargs("SQ=%s", path_sq) ||
            !$value$plusargs("COEFF=%s", path_coeff))
            $fatal(1, "missing test vector arguments");
        if (input_count < 1 || output_count != input_count+N_TAPS-1 || output_count > MAX_SAMPLES)
            $fatal(1, "invalid vector sizes");
        max_cycles = output_count*(N_TAPS+20)*3 + 1000;
        #1;
        if (!USE_DEFAULT_COEFF) $readmemh(path_coeff, dut.coefficients, 0, N_TAPS-1);
        check_round(36'sd0, 17'h00000);
        check_round(36'sd65535, 17'h00000);
        check_round(36'sd65536, 17'h00000);
        check_round(36'sd65537, 17'h00001);
        check_round(36'sd196607, 17'h00001);
        check_round(36'sd196608, 17'h00002);
        check_round(36'sd196609, 17'h00002);
        check_round(36'sd327680, 17'h00002);
        check_round(-36'sd65535, 17'h00000);
        check_round(-36'sd65536, 17'h00000);
        check_round(-36'sd65537, 17'h0ffff);
        check_round(-36'sd196607, 17'h0ffff);
        check_round(-36'sd196608, 17'h0fffe);
        check_round(-36'sd196609, 17'h0fffe);
        check_round(-36'sd327680, 17'h0fffe);
        check_round(36'sd4294901759, 17'h07fff);
        check_round(36'sd4294901760, 17'h17fff);
        check_round(36'sd4294901761, 17'h17fff);
        check_round(-36'sd4295032832, 17'h08000);
        check_round(-36'sd4295032833, 17'h18000);
        check_round(36'sd34359738367, 17'h17fff);
        check_round(-36'sd34359738368, 17'h18000);
        $readmemh(path_i, input_i, 0, input_count-1);
        $readmemh(path_q, input_q, 0, input_count-1);
        $readmemh(path_ei, expected_i, 0, output_count-1);
        $readmemh(path_eq, expected_q, 0, output_count-1);
        $readmemh(path_si, expected_sat_i, 0, output_count-1);
        $readmemh(path_sq, expected_sat_q, 0, output_count-1);
        reset_dut();
        send_probe();
        // For one tap, one MAC edge has not yet occurred at this negedge;
        // for longer filters, reset well before the output would be produced.
        rst_n = 0;
        reset_dut();
        send_probe();
        wait (m_valid === 1);
        repeat (4) @(posedge clk);
        reset_dut();
        phase = 1;
        while (received < output_count) begin
            @(negedge clk);
            rng = {rng[30:0], rng[31]^rng[21]^rng[1]^rng[0]};
            m_ready = RANDOM_STALLS ? rng[0] | rng[3] : 1'b1;
            if (sent < output_count) begin
                if (!s_valid || accepted_last_edge)
                    s_valid = RANDOM_STALLS ? rng[2] | rng[5] : 1'b1;
                s_i = (sent < input_count) ? input_i[sent] : 12'd0;
                s_q = (sent < input_count) ? input_q[sent] : 12'd0;
            end else s_valid = 0;
        end
        @(negedge clk);
        s_valid = 0; m_ready = 1;
        repeat (N_TAPS+3) @(posedge clk);
        #1;
        if (sent != output_count || m_valid !== 0) $fatal(1, "unfinished or extra transaction");
        $display("PASS case=%0s taps=%0d accepted=%0d received=%0d valid_after_cycles=%0d handshake_min=%0d handshake_max=%0d output_stall_cycles=%0d input_wait_cycles=%0d reset_during_mac=1 reset_stalled_output=1 rounding_checks=%0d random_stalls=%0d default_coeff=%0d",
            case_name,N_TAPS,sent,received,N_TAPS,min_handshake_cycles,max_handshake_cycles,
            stalled_output_cycles,input_wait_cycles,rounding_checks,RANDOM_STALLS,USE_DEFAULT_COEFF);
        $finish;
    end
endmodule
