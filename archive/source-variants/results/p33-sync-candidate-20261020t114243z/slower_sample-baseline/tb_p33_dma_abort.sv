`timescale 1ns/1ps
// Digital fixture for cooperative AXI drain, canceled descriptor resync,
// fresh payload epochs, and common reset with sample clock paused at release.
module p33_abort_case #(parameter integer TX=0)(output reg done);
  reg qclk=0,fclk=0,rst=0,enable=0,pause_sample=0,drain_fifo=0;
  always #5 qclk=~qclk;
  initial begin #0.731;forever begin #27.1;if(!pause_sample)fclk=~fclk;end end
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
  integer epoch=0,sent=0,received=0,eots=0,issued=0,target=0,read_sent=0;
  integer awcursor=0,arcursor=0,wremaining=0,rremaining=0;
  integer fcycles=0,qcycles=0,bdelay=0,stalls=0,enable_cycles=0;
  integer sync_events=0,checked_beats=0,normal_epochs=0,aborts=0;
  reg wactive=0,ractive=0,raccepted=0;
  reg [31:0] rng=32'h5ba81291;
  reg old_aw_stall=0,old_w_stall=0,old_ar_stall=0;
  reg [31:0] old_awaddr=0,old_araddr=0;
  reg [7:0] old_awlen=0,old_arlen=0;
  reg [63:0] old_wdata=0;
  reg old_wlast=0;
  function automatic [63:0] pattern(input integer ep,input integer n);
    pattern={32'h91a2e7bd^(ep*32'h101123a7)^(n*32'h45d9f3b),32'h3f61a4cd^(ep*32'hf1d3297)^(n*32'h9e3779b1)};
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
  always @(posedge qclk)begin
    if(!rst)begin
      wactive=0;ractive=0;wremaining=0;rremaining=0;bdelay=0;
      raccepted=0;
      old_aw_stall=0;old_w_stall=0;old_ar_stall=0;
    end else begin
      qcycles=qcycles+1;
      raccepted=rvalid && rready;
      if(eot)eots=eots+1;
      if(dut.sync_id)sync_events=sync_events+1;
      if(old_aw_stall && (!awvalid || awaddr!==old_awaddr || awlen!==old_awlen))$fatal(1,"AW changed under stall TX=%0d",TX);
      if(old_ar_stall && (!arvalid || araddr!==old_araddr || arlen!==old_arlen))$fatal(1,"AR changed under stall TX=%0d",TX);
      if(old_w_stall && (!wvalid || wdata!==old_wdata || wlast!==old_wlast || wstrb!==8'hff))$fatal(1,"W changed under stall TX=%0d",TX);
      old_aw_stall=awvalid && !awready;old_awaddr=awaddr;old_awlen=awlen;
      old_ar_stall=arvalid && !arready;old_araddr=araddr;old_arlen=arlen;
      old_w_stall=wvalid && !wready;old_wdata=wdata;old_wlast=wlast;
      if(awvalid && awready)begin
        if(awaddr!==awcursor*8 || awsize!==3)$fatal(1,"RX AXI address mismatch");
        awcursor=awcursor+awlen+1;wremaining=awlen+1;wactive=1;
      end
      if(wvalid && !wready)stalls=stalls+1;
      if(wvalid && wready)begin
        if(!wactive || wremaining==0)$fatal(1,"RX write without address");
        if(wdata!==pattern(epoch,received) || wstrb!==8'hff)$fatal(1,"RX stale/corrupt epoch=%0d beat=%0d",epoch,received);
        if(wlast!==(wremaining==1))$fatal(1,"RX WLAST mismatch");
        received=received+1;checked_beats=checked_beats+1;wremaining=wremaining-1;
        if(wremaining==0)begin wactive=0;bdelay=7;end
      end
      if(bvalid && bready)bdelay=0;else if(bdelay>1)bdelay=bdelay-1;
      if(arvalid && arready)begin
        if(araddr!==arcursor*8 || arsize!==3)$fatal(1,"TX AXI address mismatch");
        arcursor=arcursor+arlen+1;rremaining=arlen+1;ractive=1;
      end
      if(rvalid && rready)begin read_sent=read_sent+1;rremaining=rremaining-1;if(rremaining==0)ractive=0;end
    end
  end
  always @(negedge qclk)begin
    rng={rng[30:0],rng[31]^rng[21]^rng[1]^rng[0]};
    awready<=rst && !TX && !wactive && bdelay==0 && !bvalid && rng[1];
    wready<=rst && !TX && wactive && qcycles%41<29 && rng[2:1]!=0;
    bvalid<=rst && !TX && bdelay==1;
    arready<=rst && TX && !ractive && !rvalid && rng[2];
    if(!rst)begin rvalid<=0;rdata<=0;end
    // Retain a beat only when the preceding active edge did NOT accept it.
    // The DUT may deassert READY after an accepted final beat; sampling READY
    // at this falling edge would incorrectly retain/replay that beat.
    else if(rvalid && !raccepted)begin end
    else begin rvalid<=TX && ractive && rng[1:0]!=0;rdata<=pattern(epoch,read_sent);end
  end
  always @(posedge fclk)begin
    if(!enable)enable_cycles=0;else enable_cycles=enable_cycles+1;
    if(rst && wr_en)sent=sent+1;
  end
  always @(negedge fclk)begin
    fcycles=fcycles+1;
    if(rst && TX && rd_valid)begin
      if(rd_data!==pattern(epoch,received))$fatal(1,"TX stale/corrupt epoch=%0d beat=%0d",epoch,received);
      received=received+1;checked_beats=checked_beats+1;
    end
    // One edge of external FIFO activity may remain at disable. Overflow /
    // underflow then reports cancellation, not successful payload delivery.
    if(rst && enable && overflow)$fatal(1,"normal RX producer overflow");
    if(rst && enable && TX && underflow)$fatal(1,"normal TX consumer underflow");
    wr_en<=rst && !TX && enable && wr_request && p33_wr_high_edges>=3 && sent<target && fcycles%4==0;
    wr_data<=pattern(epoch,sent);
    rd_en<=rst && TX && (enable || drain_fifo) && rd_request && received<target && fcycles%4==0 && (drain_fifo || enable_cycles>20);
  end
  task automatic quiet;
    integer k;reg ok;
    begin
      ok=0;
      for(k=0;k<10000;k=k+1)begin
        @(negedge qclk);
        if(!dut.do_enable && !dut.enabled && !dut.enabled_src && !dut.enabled_dest &&
          dut.req_src_empty && dut.req_dest_empty && dut.fifo_empty &&
          dut.request_id==dut.response_id && !dut.sync_id &&
          !dut.sync_id_ret_src && !dut.sync_id_ret_dest &&
          !wactive && bdelay==0 && !bvalid && !ractive && !rvalid &&
          !awvalid && !arvalid && !wvalid)begin ok=1;k=10000;end
      end
      if(!ok)$fatal(1,"QUIET_TIMEOUT TX=%0d epoch=%0d dbg=%h req=%d resp=%d W=%0d R=%0d qsrc=%b qdst=%b ractive=%b rvalid=%b AW=%b AR=%b Wvalid=%b",TX,epoch,dut.dbg_status,dut.request_id,dut.response_id,wremaining,rremaining,dut.req_src_empty,dut.req_dest_empty,ractive,rvalid,awvalid,arvalid,wvalid);
      repeat(30)@(negedge qclk);
    end
  endtask
  task automatic new_epoch(input integer tag,input integer count);
    begin
      @(negedge qclk);epoch=tag;target=count;
      sent=0;received=0;read_sent=0;eots=0;issued=0;awcursor=0;arcursor=0;
      address=0;req_valid=0;enable=1;
    end
  endtask
  task automatic submit(input integer start,input integer count);
    integer k;reg accepted;
    begin
      @(negedge qclk);address=start;length=count*8-1;req_valid=1;accepted=0;
      for(k=0;k<10000;k=k+1)begin
        @(posedge qclk);if(req_ready)begin accepted=1;k=10000;end
      end
      if(!accepted)$fatal(1,"request timeout TX=%0d epoch=%0d",TX,epoch);
      issued=issued+1;@(negedge qclk);req_valid=0;
    end
  endtask
  task automatic normal(input integer tag);
    integer n,count,pos,k;reg complete;
    begin
      new_epoch(tag,1108);pos=0;
      for(n=0;n<32;n=n+1)begin
        case(n%8)
          0:count=1;1:count=2;2:count=15;3:count=16;4:count=17;5:count=33;6:count=64;7:count=129;
        endcase
        submit(pos,count);pos=pos+count;
      end
      complete=0;
      for(k=0;k<100000;k=k+1)begin
        @(negedge qclk);if(received==target && eots==32)begin complete=1;k=100000;end
      end
      if(!complete)$fatal(1,"normal transfer timeout TX=%0d epoch=%0d got=%0d eot=%0d",TX,epoch,received,eots);
      drain_fifo=1;enable=0;quiet();drain_fifo=0;normal_epochs=normal_epochs+1;
      $display("P33_NORMAL_PASS TX=%0d epoch=%0d desc=32 beats=%0d",TX,tag,received);
    end
  endtask

  integer p33_wr_high_edges=0;
  always @(posedge fclk)begin
    if(!rst || !enable || !wr_request)p33_wr_high_edges<=0;
    else if(p33_wr_high_edges<3)p33_wr_high_edges<=p33_wr_high_edges+1;
  end


  // Identical additional invariants in baseline and candidate cases.
  reg p33_prior_valid=0, p33_prior_do_enable=0;
  reg [2:0] p33_prior_request_id=0;
  integer p33_gate_checks=0,p33_frozen_tail_checks=0;
  always @(posedge qclk)begin
    if(!rst)begin
      p33_prior_valid=0;
      p33_prior_do_enable=0;
      p33_prior_request_id=0;
    end else begin
      p33_gate_checks=p33_gate_checks+1;
      if(dut.do_enable && (dut.sync_id || dut.sync_id_ret_src || dut.sync_id_ret_dest))
        $fatal(1,"P33_GATE_INVARIANT TX=%0d sync=%b src_ack=%b dest_ack=%b",
          TX,dut.sync_id,dut.sync_id_ret_src,dut.sync_id_ret_dest);
      // Evaluate pre-NBA values: current ID reflects the previous active edge.
      if(p33_prior_valid && !p33_prior_do_enable)begin
        p33_frozen_tail_checks=p33_frozen_tail_checks+1;
        if(dut.request_id !== p33_prior_request_id)
          $fatal(1,"P33_TAIL_MOVED_WHILE_DISABLED TX=%0d old=%h new=%h",
            TX,p33_prior_request_id,dut.request_id);
      end
      p33_prior_valid=1;
      p33_prior_do_enable=dut.do_enable;
      p33_prior_request_id=dut.request_id;
    end
  end
  always @(posedge done)begin
    $display("P33_LOCAL_INVARIANTS_PASS TX=%0d gate_checks=%0d frozen_tail_checks=%0d",TX,p33_gate_checks,p33_frozen_tail_checks);
  end

  integer before_sync,k;reg observed;
  initial begin
    done=0;
    repeat(30)@(negedge qclk);rst=1;repeat(30)@(negedge qclk);
    normal(1);
    new_epoch(2,2048);submit(0,2048);observed=0;
    for(k=0;k<100000;k=k+1)begin
      @(negedge qclk);
      if((TX && rvalid && !rready && read_sent>16) || (!TX && wvalid && !wready && received>4))begin observed=1;k=100000;end
    end
    if(!observed)$fatal(1,"abort stall not exercised TX=%0d",TX);
    before_sync=sync_events;drain_fifo=1;enable=0;req_valid=0;
    quiet();drain_fifo=0;
    if(sync_events==before_sync)$fatal(1,"abort did not exercise ID resync TX=%0d",TX);
    if(received>=2048)$fatal(1,"abort descriptor was not canceled TX=%0d",TX);
    aborts=aborts+1;
    $display("P33_ABORT_PASS TX=%0d delivered_prefix=%0d memory_read=%0d sync_cycles=%0d",TX,received,read_sent,sync_events-before_sync);
    normal(3);
    // Reset all AXI participants together. The sample clock remains paused
    // after req reset release, testing staggered deassertion without pretending
    // that a one-sided reset of a live AXI slave is a legal bus transaction.
    new_epoch(4,2048);submit(0,2048);
    wait((TX && read_sent>32) || (!TX && sent>32));
    @(negedge qclk);enable=0;req_valid=0;rst=0;pause_sample=1;wr_en=0;rd_en=0;
    repeat(30)@(negedge qclk);rst=1;
    repeat(20)@(negedge qclk);
    if(dut.do_enable || awvalid || arvalid || wvalid)$fatal(1,"activity during paused reset release");
    pause_sample=0;repeat(15)@(negedge fclk);quiet();
    normal(5);
    $display("P33_ABORT_RESET_CASE_PASS TX=%0d clean_epochs=%0d aborts=%0d paused_reset=1 checked_beats=%0d",TX,normal_epochs,aborts,checked_beats);
    done=1;
  end
endmodule
module tb_p33_dma_abort;
  wire [1:0] done;
  p33_abort_case #(.TX(0)) rx(done[0]);
  p33_abort_case #(.TX(1)) tx(done[1]);
  initial begin wait(&done);$display("P33_ABORT_RESET_TB_PASS cases=2");$finish;end
  initial begin #15000000;$fatal(1,"global timeout");end
endmodule
