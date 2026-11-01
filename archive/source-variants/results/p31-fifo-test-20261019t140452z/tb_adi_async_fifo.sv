`timescale 1ns/1ps
// Test the unchanged ADI FIFO used by DMA request, response and payload paths.
// Digital simulation does not model analog metastability or validate placement.
module fifo_case #(parameter integer ID=0, AW=0, WIDTH=40,
                   parameter real SHALF=5.0, MHALF=3.2)(output reg done=0);
  reg sclk=0,mclk=0,sresetn=0,mresetn=0,produce=0,consume=0;
  always #(SHALF) sclk=~sclk;
  initial begin #(0.37+ID*0.113); forever #(MHALF) mclk=~mclk; end
  reg valid=0,ready=0;
  reg [WIDTH-1:0] data=0;
  wire sready,mvalid,empty;
  wire [WIDTH-1:0] output_data;
  wire [AW:0] room,level;
  util_axis_fifo #(.DATA_WIDTH(WIDTH),.ADDRESS_WIDTH(AW),.ASYNC_CLK(1)) dut(
    .s_axis_aclk(sclk),.s_axis_aresetn(sresetn),.s_axis_valid(valid),
    .s_axis_ready(sready),.s_axis_data(data),.s_axis_empty(empty),.s_axis_room(room),
    .m_axis_aclk(mclk),.m_axis_aresetn(mresetn),.m_axis_ready(ready),
    .m_axis_valid(mvalid),.m_axis_data(output_data),.m_axis_level(level));
  reg [WIDTH-1:0] expected[0:39999];
  integer wr=0,rd=0,total_checked=0,source_stalls=0,dest_stalls=0;
  integer epoch=0;
  reg [31:0] sprng=32'h8ab5c1d3 ^ (ID*7919);
  reg [31:0] mprng=32'h53109f8d ^ (ID*1259);
  reg was_stalled=0;
  reg [WIDTH-1:0] previous_data=0;
  function automatic [31:0] step(input [31:0] x);
    step={x[30:0],x[31]^x[21]^x[1]^x[0]};
  endfunction
  function automatic [WIDTH-1:0] pattern(input integer n,input integer e);
    reg [63:0] v;
    begin
      v={32'hd3a56127^(n*32'h9e3779b1),32'ha78b1d63^(n*32'h45d9f3b)};
      pattern=v ^ (64'h2315c8aa784d38f1*e);
    end
  endfunction
  always @(negedge sclk) begin
    sprng=step(sprng);
    if(!sresetn) begin valid<=0;data<=0;end
    else if(valid && !sready) begin end
    else begin
      valid<=produce && sprng[2:0]!=0;
      data<=pattern(wr,epoch);
    end
  end
  always @(posedge sclk) begin
    if(!sresetn)wr=0;
    else if(valid && sready)begin
      if(wr>=40000)$fatal(1,"case %0d scoreboard overflow",ID);
      expected[wr]=data;wr=wr+1;
    end
    else if(valid && !sready)source_stalls=source_stalls+1;
  end
  always @(negedge mclk)begin
    mprng=step(mprng);
    ready<=mresetn && consume && mprng[2:0]>2;
  end
  always @(posedge mclk)begin
    if(!mresetn)begin rd=0;was_stalled=0;end
    else begin
      if(was_stalled && (!mvalid || output_data!==previous_data))
        $fatal(1,"case %0d output changed while stalled",ID);
      was_stalled=mvalid && !ready;
      previous_data=output_data;
      if(mvalid && ready)begin
        if(rd>=wr)$fatal(1,"case %0d unsolicited/duplicate data rd=%0d wr=%0d",ID,rd,wr);
        if(output_data!==expected[rd])
          $fatal(1,"case %0d mismatch epoch=%0d index=%0d got=%h expected=%h",ID,epoch,rd,output_data,expected[rd]);
        rd=rd+1;total_checked=total_checked+1;
      end
      if(mvalid && !ready)dest_stalls=dest_stalls+1;
    end
  end
  task automatic reset_both;
    begin
      produce=0;consume=0;sresetn=0;mresetn=0;
      repeat(20)@(negedge sclk);
      // Reset release is deliberately skewed; traffic waits for both clocks.
      sresetn=1;repeat(13)@(negedge mclk);mresetn=1;
      repeat(16)@(negedge sclk);
      if(mvalid!==0 || empty!==1)$fatal(1,"case %0d failed reset/empty",ID);
    end
  endtask
  initial begin
    reset_both();
    for(epoch=1;epoch<=3;epoch=epoch+1)begin
      produce=1;consume=1;
      wait(wr>=2000);@(negedge sclk);produce=0;
      wait(!valid);wait(rd==wr);
      repeat(20)@(negedge mclk);
      if(mvalid!==0 || empty!==1)$fatal(1,"case %0d did not drain",ID);
      $display("P31_FIFO_EPOCH case=%0d epoch=%0d accepted=%0d checked=%0d",ID,epoch,wr,rd);
      // Force an occupied FIFO before a coordinated reset; in-flight values
      // are explicitly abandoned by the reset, not counted as valid delivery.
      produce=1;consume=0;
      repeat(60)@(negedge sclk);
      if(wr==rd)$fatal(1,"case %0d reset scenario never became occupied",ID);
      reset_both();
    end
    if(total_checked<6000 || source_stalls==0 || dest_stalls==0)
      $fatal(1,"case %0d insufficient coverage",ID);
    $display("P31_FIFO_CASE_PASS case=%0d AW=%0d WIDTH=%0d checked=%0d source_stalls=%0d dest_stalls=%0d resets=4",ID,AW,WIDTH,total_checked,source_stalls,dest_stalls);
    done=1;
  end
endmodule

module tb_adi_async_fifo;
  wire [5:0] done;
  fifo_case #(.ID(0),.AW(0),.WIDTH(40),.SHALF(5.0),.MHALF(3.2)) c0(done[0]);
  fifo_case #(.ID(1),.AW(0),.WIDTH(40),.SHALF(3.2),.MHALF(5.0)) c1(done[1]);
  fifo_case #(.ID(2),.AW(0),.WIDTH(1),.SHALF(5.0),.MHALF(4.1)) c2(done[2]);
  fifo_case #(.ID(3),.AW(0),.WIDTH(1),.SHALF(4.1),.MHALF(5.0)) c3(done[3]);
  fifo_case #(.ID(4),.AW(7),.WIDTH(64),.SHALF(5.0),.MHALF(3.2)) c4(done[4]);
  fifo_case #(.ID(5),.AW(7),.WIDTH(64),.SHALF(3.2),.MHALF(5.0)) c5(done[5]);
  initial begin wait(&done);$display("P31_FIFO_TB_PASS cases=6");$finish;end
  initial begin #10000000;$fatal(1,"global timeout");end
endmodule
