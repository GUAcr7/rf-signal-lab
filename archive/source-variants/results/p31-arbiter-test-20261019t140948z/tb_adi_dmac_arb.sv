`timescale 1ns/1ps
// Unchanged request_arb with asynchronous AXIS endpoints. This covers EOT and
// request-ID handshakes; the board uses FIFO/MM endpoints, tested separately.
module arb_case #(parameter integer ID=0,parameter real SHALF=3.6,MHALF=6.3)(output reg done=0);
  reg qclk=0,sclk=0,mclk=0,resetn=0,enable=0;
  always #5 qclk=~qclk;
  initial begin #0.173;forever #(SHALF)sclk=~sclk;end
  initial begin #0.619;forever #(MHALF)mclk=~mclk;end
  reg request_valid=0;
  wire request_ready,eot;
  reg [23:0] length=0;
  reg source_valid=0,sink_ready=0;
  wire source_ready,sink_valid,last;
  reg [63:0] source_data=0;
  wire [63:0] sink_data;
  integer sent=0,received=0,eots=0,requested=0;
  integer sizes[0:127],boundaries[0:127],total=0,packet=0,stall_cycles=0;
  reg [31:0] srng=32'had512384^(ID*991),mrng=32'h1938abcd^(ID*757);
  integer mcycles=0;
  function automatic [63:0] pattern(input integer n);
    pattern={32'h159c4b3a^(n*32'h9e3779b1),32'h7523cbd8^(n*32'h45d9f3b)};
  endfunction
  function automatic [31:0] step(input [31:0] x);
    step={x[30:0],x[31]^x[21]^x[1]^x[0]};
  endfunction
  dmac_request_arb #(.DMA_TYPE_SRC(1),.DMA_TYPE_DEST(1),.DMA_DATA_WIDTH_SRC(64),
    .DMA_DATA_WIDTH_DEST(64),.ASYNC_CLK_REQ_SRC(1),.ASYNC_CLK_DEST_REQ(1),.ASYNC_CLK_SRC_DEST(1)) dut(
    .req_aclk(qclk),.req_aresetn(resetn),.req_valid(request_valid),.req_ready(request_ready),
    .req_dest_address(29'b0),.req_src_address(29'b0),.req_length(length),
    .req_xlast(1'b1),.req_sync_transfer_start(1'b0),.eot(eot),.enable(enable),.pause(1'b0),
    .m_dest_axi_aclk(qclk),.m_dest_axi_aresetn(resetn),.m_src_axi_aclk(qclk),.m_src_axi_aresetn(resetn),
    .m_axi_awready(1'b0),.m_axi_wready(1'b0),.m_axi_bvalid(1'b0),.m_axi_bresp(2'b0),
    .m_axi_arready(1'b0),.m_axi_rdata(64'b0),.m_axi_rvalid(1'b0),.m_axi_rresp(2'b0),
    .s_axis_aclk(sclk),.s_axis_valid(source_valid),.s_axis_ready(source_ready),.s_axis_data(source_data),
    .s_axis_last(1'b0),.s_axis_user(1'b1),.m_axis_aclk(mclk),.m_axis_ready(sink_ready),
    .m_axis_valid(sink_valid),.m_axis_data(sink_data),.m_axis_last(last),
    .fifo_wr_clk(sclk),.fifo_wr_en(1'b0),.fifo_wr_din(64'b0),.fifo_wr_sync(1'b0),
    .fifo_rd_clk(mclk),.fifo_rd_en(1'b0));
  always @(posedge qclk)if(resetn && eot)eots=eots+1;
  always @(posedge sclk)if(resetn && source_valid && source_ready)sent=sent+1;
  always @(negedge sclk)begin
    srng=step(srng);
    if(!resetn)begin source_valid<=0;source_data<=0;end
    else if(source_valid && !source_ready)begin end
    else begin source_valid<=enable && sent<total && srng[1:0]!=0;source_data<=pattern(sent);end
  end
  always @(negedge mclk)begin
    mrng=step(mrng);mcycles=mcycles+1;
    // Include long blocked intervals, not just isolated random stalls.
    sink_ready<=resetn && (mcycles%311<241) && mrng[2:0]>2;
  end
  reg stalled=0,old_last=0;
  reg [63:0] old_data=0;
  always @(posedge mclk)begin
    if(!resetn)stalled=0;
    else begin
      if(stalled && (!sink_valid || sink_data!==old_data || last!==old_last))
        $fatal(1,"case %0d output changed during backpressure",ID);
      stalled=sink_valid && !sink_ready;old_data=sink_data;old_last=last;
      if(stalled)stall_cycles=stall_cycles+1;
      if(sink_valid && sink_ready)begin
        if(received>=total || received>=sent)$fatal(1,"case %0d unsolicited data",ID);
        if(sink_data!==pattern(received))$fatal(1,"case %0d corrupt/drop data at %0d",ID,received);
        if(last!==(received+1==boundaries[packet]))$fatal(1,"case %0d TLAST mismatch packet=%0d beat=%0d",ID,packet,received);
        received=received+1;
        if(last)packet=packet+1;
      end
    end
  end
  integer n;
  initial begin
    for(n=0;n<128;n=n+1)begin
      case(n%10)
        0:sizes[n]=1;1:sizes[n]=2;2:sizes[n]=8;3:sizes[n]=15;4:sizes[n]=16;
        5:sizes[n]=17;6:sizes[n]=31;7:sizes[n]=33;8:sizes[n]=64;9:sizes[n]=256;
      endcase
      total=total+sizes[n];boundaries[n]=total;
    end
    repeat(25)@(negedge qclk);resetn=1;
    repeat(30)@(negedge qclk);enable=1;
    for(n=0;n<128;n=n+1)begin
      @(negedge qclk);length=sizes[n]*8-1;request_valid=1;
      do @(posedge qclk);while(!request_ready);
      requested=requested+1;
      @(negedge qclk);request_valid=0;
    end
    wait(received==total && eots==128);
    repeat(100)@(negedge qclk);
    if(sent!=total || packet!=128 || eots!=128 || stall_cycles==0)
      $fatal(1,"case %0d inconsistent completion",ID);
    enable=0;repeat(100)@(negedge qclk);
    if(dut.enabled!==0)$fatal(1,"case %0d disable did not quiesce",ID);
    $display("P31_ARBITER_CASE_PASS case=%0d descriptors=%0d data_beats=%0d TLAST=%0d EOT=%0d stalls=%0d",ID,requested,received,packet,eots,stall_cycles);
    done=1;
  end
endmodule

module tb_adi_dmac_arb;
  wire [1:0] done;
  arb_case #(.ID(0),.SHALF(3.6),.MHALF(6.3)) a(done[0]);
  arb_case #(.ID(1),.SHALF(6.3),.MHALF(3.6)) b(done[1]);
  initial begin wait(&done);$display("P31_ARBITER_TB_PASS cases=2");$finish;end
  initial begin #10000000;$fatal(1,"global timeout");end
endmodule
