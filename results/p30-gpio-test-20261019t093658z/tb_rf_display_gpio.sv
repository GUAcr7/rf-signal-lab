`timescale 1ns/1ps
module tb_rf_display_gpio;
    reg [63:0] ps_o = 0, ps_t = 0;
    reg [14:0] rf_i = 0;
    reg touch_intr = 0;
    wire [63:0] ps_i;
    wire [14:0] rf_o, rf_t;
    wire up_enable, up_txnrx;
    integer checks = 0;
    rf_display_gpio dut(.*);
    task check_mapping;
        reg [63:0] expected;
        begin
            #1;
            expected = 0;
            expected[0] = touch_intr;
            for (integer bitno=0; bitno<15; bitno=bitno+1)
                expected[32+bitno] = rf_i[bitno];
            if (ps_i !== expected) $fatal(1, "input mapping or unused input tie failed");
            for (integer bitno=0; bitno<15; bitno=bitno+1) begin
                if (rf_o[bitno] !== ps_o[32+bitno]) $fatal(1, "RF output mapping failed");
                if (rf_t[bitno] !== ps_t[32+bitno]) $fatal(1, "RF tristate mapping failed");
            end
            if (up_enable !== ps_o[47] || up_txnrx !== ps_o[48])
                $fatal(1, "AD9361 control mapping failed");
            checks = checks + 1;
        end
    endtask
    initial begin
        check_mapping();
        ps_o='1; ps_t='1; rf_i='1; touch_intr=1; check_mapping();
        // Exhaustive one-hot walks expose swapped, dropped, or aliased bits.
        for (integer b=0; b<64; b=b+1) begin
            ps_o=64'b1<<b; ps_t=~(64'b1<<b);
            rf_i=0; touch_intr=0; check_mapping();
        end
        ps_o=0; ps_t='1;
        for (integer b=0; b<15; b=b+1) begin
            rf_i=15'b1<<b; touch_intr=0; check_mapping();
            touch_intr=1; check_mapping();
        end
        for (integer n=0; n<256; n=n+1) begin
            ps_o={$urandom,$urandom}; ps_t={$urandom,$urandom};
            rf_i=$urandom; touch_intr=$urandom; check_mapping();
        end
        $display("P30_GPIO_TB_PASS checks=%0d", checks);
        $finish;
    end
    initial #10000 $fatal(1,"timeout");
endmodule
