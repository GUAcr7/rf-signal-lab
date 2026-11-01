`timescale 1ns/1ps
// Exercise the actual generated VTC 6.2 encrypted model via AXI-Lite.
// This is a 1080p progressive generator test, not a panel/VDMA acceptance test.
module tb_vtc_runtime;
    reg clk=0, axi=0, resetn=0;
    always #3.367 clk=~clk;
    always #2.5 axi=~axi;
    reg [8:0] awaddr=0,araddr=0;
    reg awvalid=0,wvalid=0,arvalid=0;
    reg [31:0] wdata=0;
    wire awready,wready,bvalid,arready,rvalid;
    wire [1:0] bresp,rresp;
    wire [31:0] rdata;
    wire hs,hb,vs,vb,de,irq;
    wire [0:0] fs;
    system_v_tc_0_0 dut(.clk(clk),.clken(1'b1),.gen_clken(1'b1),.sof_state(1'b0),
        .s_axi_aclk(axi),.s_axi_aclken(1'b1),.resetn(resetn),.s_axi_aresetn(resetn),
        .hsync_out(hs),.hblank_out(hb),.vsync_out(vs),.vblank_out(vb),.active_video_out(de),
        .s_axi_awaddr(awaddr),.s_axi_awvalid(awvalid),.s_axi_awready(awready),
        .s_axi_wdata(wdata),.s_axi_wstrb(4'hf),.s_axi_wvalid(wvalid),.s_axi_wready(wready),
        .s_axi_bresp(bresp),.s_axi_bvalid(bvalid),.s_axi_bready(1'b1),
        .s_axi_araddr(araddr),.s_axi_arvalid(arvalid),.s_axi_arready(arready),
        .s_axi_rdata(rdata),.s_axi_rresp(rresp),.s_axi_rvalid(rvalid),.s_axi_rready(1'b1),
        .irq(irq),.fsync_in(1'b0),.fsync_out(fs));
    task write_reg(input [8:0] address,input [31:0] data);
        bit adone,wdone,bdone;
        begin
            adone=0;wdone=0;bdone=0;
            @(negedge axi); awaddr=address;wdata=data;awvalid=1;wvalid=1;
            for (integer cycles=0;cycles<300;cycles=cycles+1) begin
                @(posedge axi);
                if (awvalid && awready) adone=1;
                if (wvalid && wready) wdone=1;
                if (bvalid) begin
                    if (bresp != 0) $fatal(1,"AXI write response error");
                    bdone=1;
                end
                @(negedge axi);
                if(adone) awvalid=0;
                if(wdone) wvalid=0;
                if(bdone) break;
            end
            if(!adone || !wdone || !bdone) $fatal(1,"AXI write timeout at %x",address);
        end
    endtask
    task read_check(input [8:0] address,input [31:0] expected);
        bit adone,rdone;
        begin
            adone=0;rdone=0;
            @(negedge axi);araddr=address;arvalid=1;
            for(integer cycles=0;cycles<300;cycles=cycles+1) begin
                @(posedge axi);
                if(arvalid && arready) adone=1;
                if(rvalid) begin
                    if(rresp!=0 || rdata!==expected)
                        $fatal(1,"AXI readback at %x expected %x got %x",address,expected,rdata);
                    rdone=1;
                end
                @(negedge axi);
                if(adone) arvalid=0;
                if(rdone) break;
            end
            if(!adone || !rdone) $fatal(1,"AXI read timeout");
        end
    endtask
    integer cycles=0,last_hs=0,last_vs=0,frames=0;
    integer pixels=0,line_pulses=0,de_run=0,min_de=99999,max_de=0;
    integer hs_checks=0;
    bit old_hs=0,old_vs=0,old_de=0,started=0,monitor=0;
    always @(posedge clk) begin
        #0.001;
        cycles=cycles+1;
        if(monitor) begin
            if(cycles%500000==0) $display("P30_VTC_PROGRESS cycles=%0d frames=%0d",cycles,frames);
            if(hs && !old_hs) begin
                if(last_hs!=0) begin
                    if(cycles-last_hs!=2200) $fatal(1,"horizontal period mismatch");
                    hs_checks=hs_checks+1;
                end
                last_hs=cycles;
            end
            if(vs && !old_vs) begin
                if(started) begin
                    if(cycles-last_vs!=2200*1125) $fatal(1,"vertical period mismatch");
                    if(pixels!=1920*1080) $fatal(1,"active pixels mismatch: %0d",pixels);
                    if(line_pulses!=1080 || min_de!=1920 || max_de!=1920)
                        $fatal(1,"partial active line: lines=%0d min=%0d max=%0d",line_pulses,min_de,max_de);
                    frames=frames+1;
                    $display("P30_VTC_FRAME frame=%0d pixels=%0d lines=%0d DE=%0d..%0d",frames,pixels,line_pulses,min_de,max_de);
                end
                started=1;last_vs=cycles;pixels=0;line_pulses=0;min_de=99999;max_de=0;
            end
            if(started) begin
                if(de) begin pixels=pixels+1;de_run=de_run+1;end
                if(!de && old_de) begin
                    line_pulses=line_pulses+1;
                    if(de_run<min_de) min_de=de_run;
                    if(de_run>max_de) max_de=de_run;
                    de_run=0;
                end
                if(frames==2) begin
                    if(hs_checks<2200) $fatal(1,"insufficient line coverage");
                    $display("P30_VTC_RUNTIME_TB_PASS frames=%0d hperiod_checks=%0d",frames,hs_checks);
                    $finish;
                end
            end
            old_hs=hs;old_vs=vs;old_de=de;
        end
    end
    initial begin
        repeat(20) @(negedge axi);resetn=1;
        repeat(40) @(negedge axi);
        // Read upgraded defaults before programming; retain evidence of changes.
        read_check(9'h07c,{16'd960,16'd960});
        read_check(9'h084,{16'd1004,16'd1004});
        // Explicit 1080p progressive runtime profile. PG016 generator registers.
        write_reg(9'h000,0);
        write_reg(9'h060,{16'd1080,16'd1920});
        write_reg(9'h068,0); // YUV/RGB progressive encoding / no interlace.
        write_reg(9'h06c,32'h3f);
        write_reg(9'h070,2200);
        write_reg(9'h074,{16'd1125,16'd1125});
        write_reg(9'h078,{16'd2052,16'd2008});
        write_reg(9'h07c,{16'd1920,16'd1920});
        write_reg(9'h080,{16'd1088,16'd1083});
        write_reg(9'h084,{16'd1920,16'd1920});
        write_reg(9'h088,{16'd1920,16'd1920});
        write_reg(9'h08c,{16'd1088,16'd1083});
        write_reg(9'h090,{16'd1920,16'd1920});
        read_check(9'h07c,{16'd1920,16'd1920});
        read_check(9'h084,{16'd1920,16'd1920});
        // Select generator values, update shadow regs, enable generator only.
        write_reg(9'h000,32'h07f7ef06); // INTERLACE and SYNC_ENABLE remain clear.
        monitor=1;
    end
    initial #60000000 $fatal(1,"VTC simulation timeout");
endmodule
