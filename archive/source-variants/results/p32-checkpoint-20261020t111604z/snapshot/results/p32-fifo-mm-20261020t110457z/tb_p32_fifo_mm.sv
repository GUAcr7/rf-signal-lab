`timescale 1ns/1ps
// Actual ADI request arbiter endpoint types and slice/clock parameters.
// Conservative FIFO producer/consumer rate; this is not ADC throughput proof.
module p32_fifo_mm_case #(parameter integer TX=0)(output reg done=0);
  reg qclk=0,fclk=0,rst=0,enable=0;
  always #5 qclk=~qclk;
  initial begin #0.731;forever #16.3 fclk=~fclk;end
  reg req_valid=0;
  wire req_ready,eot;
  reg [23:0] length=0;
  reg [28:0] address=0;
  wire [31:0] awaddr,araddr;
  wire [7:0] awlen,arlen,wstrb;
  wire [2:0] awsize,arsize;
  wire awvalid,wvalid,wlast,bready,arvalid,rready;
  wire [63:0] wdata;
  reg awready=0,wready=0,bvalid=0,arready=0,rvalid=0;
  reg [63:0] rdata=0;
  reg wr_en=0,rd_en=0;
  wire overflow,underflow,wr_request,rd_request,rd_valid;
  wire [63:0] rd_data;
  reg [63:0] wr_data=0;
  integer sent=0,received=0,eots=0,issued=0,target=0;
  integer sizes[0:63],limits[0:63];
  integer awcursor=0,arcursor=0,wremaining=0,rremaining=0;
  integer fcycles=0,qcycles=0,bdelay=0,stalls=0,read_sent=0;
  reg wactive=0,ractive=0;
  reg [31:0] rng=32'h5ba81291;
  function automatic [63:0] pattern(input integer n);
    pattern={32'h91a2e7bd^(n*32'h45d9f3b),32'h3f61a4cd^(n*32'h9e3779b1)};
  endfunction
  dmac_request_arb #(.DMA_TYPE_SRC(TX?0:2),.DMA_TYPE_DEST(TX?2:0),
    .DMA_DATA_WIDTH_SRC(64),.DMA_DATA_WIDTH_DEST(64),.FIFO_SIZE(4),
    .MAX_BYTES_PER_BURST(128),.AXI_SLICE_SRC(0),.AXI_SLICE_DEST(TX?1:0),
    .ASYNC_CLK_REQ_SRC(TX?0:1),.ASYNC_CLK_DEST_REQ(TX?1:0),.ASYNC_CLK_SRC_DEST(1)) dut(
    .req_aclk(qclk),.req_aresetn(rst),.enable(enable),.pause(1'b0),
    .req_valid(req_valid),.req_ready(req_ready),.req_length(length),
    .req_src_address(address),.req_dest_address(address),
    .req_xlast(1'b1),.req_sync_transfer_start(1'b0),.eot(eot),
    .m_dest_axi_aclk(qclk),.m_dest_axi_aresetn(rst),
    .m_src_axi_aclk(qclk),.m_src_axi_aresetn(rst),
    .m_axi_awaddr(awaddr),.m_axi_awlen(awlen),.m_axi_awsize(awsize),
    .m_axi_awvalid(awvalid),.m_axi_awready(awready),
    .m_axi_wdata(wdata),.m_axi_wstrb(wstrb),.m_axi_wlast(wlast),
    .m_axi_wvalid(wvalid),.m_axi_wready(wready),
    .m_axi_bvalid(bvalid),.m_axi_bready(bready),.m_axi_bresp(2'b0),
    .m_axi_araddr(araddr),.m_axi_arlen(arlen),.m_axi_arsize(arsize),
    .m_axi_arvalid(arvalid),.m_axi_arready(arready),
    .m_axi_rdata(rdata),.m_axi_rvalid(rvalid),.m_axi_rready(rready),.m_axi_rresp(2'b0),
    .s_axis_aclk(fclk),.s_axis_valid(1'b0),.s_axis_data(64'b0),.s_axis_last(1'b0),.s_axis_user(1'b1),
    .m_axis_aclk(fclk),.m_axis_ready(1'b0),
    .fifo_wr_clk(fclk),.fifo_wr_en(wr_en),.fifo_wr_din(wr_data),
    .fifo_wr_sync(1'b0),.fifo_wr_overflow(overflow),.fifo_wr_xfer_req(wr_request),
    .fifo_rd_clk(fclk),.fifo_rd_en(rd_en),.fifo_rd_dout(rd_data),
    .fifo_rd_valid(rd_valid),.fifo_rd_underflow(underflow),.fifo_rd_xfer_req(rd_request));
  always @(posedge qclk)if(rst)begin
    qcycles=qcycles+1;
    if(eot)eots=eots+1;
    if(awvalid && awready)begin
      if(awaddr!==awcursor*8 || awsize!==3)$fatal(1,"RX AXI address/size mismatch");
      awcursor=awcursor+awlen+1;wremaining=awlen+1;wactive=1;
    end
    if(wvalid && !wready)stalls=stalls+1;
    if(wvalid && wready)begin
      if(!wactive || wremaining==0)$fatal(1,"write without accepted address");
      if(wdata!==pattern(received) || wstrb!==8'hff)$fatal(1,"RX data mismatch beat %0d",received);
      if(wlast!==(wremaining==1))$fatal(1,"RX WLAST mismatch");
      received=received+1;wremaining=wremaining-1;
      if(wremaining==0)begin wactive=0;bdelay=7;end
    end
    if(bvalid && bready)bdelay=0;
    else if(bdelay>1)bdelay=bdelay-1;
    if(arvalid && arready)begin
      if(araddr!==arcursor*8 || arsize!==3)$fatal(1,"TX AXI address/size mismatch");
      arcursor=arcursor+arlen+1;rremaining=arlen+1;ractive=1;
    end
    if(rvalid && rready)begin
      read_sent=read_sent+1;rremaining=rremaining-1;
      if(rremaining==0)ractive=0;
    end
  end
  always @(negedge qclk)begin
    rng={rng[30:0],rng[31]^rng[21]^rng[1]^rng[0]};
    awready<=rst && !TX && !wactive && bdelay==0 && !bvalid && rng[1];
    wready<=rst && !TX && wactive && qcycles%41<29 && rng[2:1]!=0;
    bvalid<=rst && !TX && bdelay==1;
    arready<=rst && TX && !ractive && !rvalid && rng[2];
    if(!rst)begin rvalid<=0;rdata<=0;end
    else if(rvalid && !rready)begin end
    else begin rvalid<=TX && ractive && rng[1:0]!=0;rdata<=pattern(read_sent);end
  end
  always @(posedge fclk)if(rst && wr_en)sent=sent+1;
  always @(negedge fclk)begin
    fcycles=fcycles+1;
    if(rst && TX && rd_valid)begin
      if(received>=target || rd_data!==pattern(received))$fatal(1,"TX FIFO mismatch beat %0d",received);
      received=received+1;
    end
    if(rst && overflow)$fatal(1,"conservative RX producer overflow");
    if(rst && TX && underflow)$fatal(1,"prefilled TX consumer underflow");
    wr_en<=rst && !TX && enable && wr_request && sent<target && fcycles%4==0;
    wr_data<=pattern(sent);
    // Allow initial prefill after each enable. Slow reads preserve headroom.
    rd_en<=rst && TX && enable && rd_request && received<target && fcycles%4==0 && enable_cycles>20;
  end
  integer enable_cycles=0;
  always @(posedge fclk)if(!enable)enable_cycles=0;else enable_cycles=enable_cycles+1;
  integer n,phase,sum=0;
  initial begin
    for(n=0;n<64;n=n+1)begin
      case(n%8)
        0:sizes[n]=1;1:sizes[n]=2;2:sizes[n]=15;3:sizes[n]=16;
        4:sizes[n]=17;5:sizes[n]=33;6:sizes[n]=64;7:sizes[n]=129;
      endcase
      sum=sum+sizes[n];limits[n]=sum;
    end
    repeat(30)@(negedge qclk);rst=1;
    repeat(30)@(negedge qclk);
    for(phase=0;phase<2;phase=phase+1)begin
      target=limits[phase*32+31];enable=1;
      for(n=phase*32;n<phase*32+32;n=n+1)begin
        @(negedge qclk);address=(n==0)?0:limits[n-1];length=sizes[n]*8-1;req_valid=1;
        do @(posedge qclk);while(!req_ready);
        issued=issued+1;@(negedge qclk);req_valid=0;
      end
      wait(received==target && eots==(phase+1)*32);
      repeat(100)@(negedge qclk);enable=0;
      repeat(150)@(negedge qclk);
      if(dut.enabled!==0)$fatal(1,"TX=%0d stop/drain failed",TX);
    end
    if((!TX && sent!=sum) || (TX && read_sent!=sum) || issued!=64 || eots!=64)
      $fatal(1,"TX=%0d accounting mismatch",TX);
    $display("P32_FIFO_MM_CASE_PASS TX=%0d desc=%0d beats=%0d EOT=%0d drained_reenable=1 stalls=%0d",TX,issued,received,eots,stalls);
    done=1;
  end
endmodule
module tb_p32_fifo_mm;
  wire [1:0] done;
  p32_fifo_mm_case #(.TX(0)) rx(done[0]);
  p32_fifo_mm_case #(.TX(1)) tx(done[1]);
  initial begin wait(&done);$display("P32_FIFO_MM_TB_PASS cases=2");$finish;end
  initial begin #10000000;$fatal(1,"global timeout");end
endmodule
