`timescale 1ns/1ps
// Offline digital test of unchanged ADI request_arb and actual FIFO/MM adapters.
// A bounded AXI3-style BFM supplies ordered, successful responses. This is NOT
// an interconnect/DDR model, analog CDC proof, or top-level cyclic-driver test.
module p32_case #(parameter integer ID=0, TX=0, parameter real RFHALF=7.1)
 (output reg done=0);
 reg qclk=0,rfclk=0,rst=0,enable=0,req_valid=0;
 always #5 qclk=~qclk;
 initial begin #0.371; forever #(RFHALF) rfclk=~rfclk; end
 reg [23:0] length=0;
 reg [28:0] address=0;
 reg sync_start=0,wr_en=0,rd_en=0,wr_sync=0;
 reg [63:0] wr_data=0;
 wire req_ready,eot,overflow,underflow,wr_xfer,rd_xfer,rd_valid;
 wire [63:0] rd_data;
 wire awvalid,wvalid,wlast,bready,arvalid,rready;
 wire [31:0] awaddr,araddr;
 wire [7:0] awlen,arlen,wstrb;
 wire [2:0] awsize,arsize;
 wire [1:0] awburst,arburst;
 wire [63:0] wdata;
 reg awready=0,wready=0,bvalid=0,arready=0,rvalid=0;
 reg [63:0] rdata=0;
 integer a_head=0,a_tail=0,r_head=0,r_tail=0,b_pending=0;
 integer a_addr[0:1023],a_count[0:1023],r_addr[0:1023],r_count[0:1023];
 integer nwrite=0,nread=0,eots=0,rcycle=0,qcycle=0;
 integer checked=0,awbursts=0,arbursts=0,wstalls=0,rstalls=0;
 integer underflows=0,overflows=0,job_base=0,job_size=0,sent=0,received=0;
 integer jobs=0,aborts=0,normal_stops=0,reset_epochs=0;
 reg checking=0,produce=0,aborting=0;
 reg [31:0] rng=32'hfabc4a13 ^ ID;
 function automatic [63:0] pattern(input integer n);
   pattern={32'hface0173^(n*32'h9e3779b1),32'hb75a11a3^(n*32'h45d9f3b)};
 endfunction
 dmac_request_arb #(.DMA_TYPE_SRC(TX?0:2),.DMA_TYPE_DEST(TX?2:0),
   .DMA_DATA_WIDTH_SRC(64),.DMA_DATA_WIDTH_DEST(64),
   .ASYNC_CLK_REQ_SRC(TX?0:1),.ASYNC_CLK_DEST_REQ(TX?1:0),
   .ASYNC_CLK_SRC_DEST(1),.AXI_LENGTH_WIDTH_SRC(4),.AXI_LENGTH_WIDTH_DEST(4),
   .AXI_SLICE_DEST(TX?1:0),.AXI_SLICE_SRC(0)) dut (
   .req_aclk(qclk),.req_aresetn(rst),.req_valid(req_valid),.req_ready(req_ready),
   .req_dest_address(address),.req_src_address(address),.req_length(length),
   .req_xlast(1'b1),.req_sync_transfer_start(sync_start),.eot(eot),.enable(enable),.pause(1'b0),
   .m_dest_axi_aclk(qclk),.m_dest_axi_aresetn(rst),.m_src_axi_aclk(qclk),.m_src_axi_aresetn(rst),
   .m_axi_awaddr(awaddr),.m_axi_awlen(awlen[3:0]),.m_axi_awsize(awsize),.m_axi_awburst(awburst),
   .m_axi_awvalid(awvalid),.m_axi_awready(awready),.m_axi_wdata(wdata),.m_axi_wstrb(wstrb),
   .m_axi_wready(wready),.m_axi_wvalid(wvalid),.m_axi_wlast(wlast),
   .m_axi_bvalid(bvalid),.m_axi_bresp(2'b0),.m_axi_bready(bready),
   .m_axi_arready(arready),.m_axi_arvalid(arvalid),.m_axi_araddr(araddr),
   .m_axi_arlen(arlen[3:0]),.m_axi_arsize(arsize),.m_axi_arburst(arburst),
   .m_axi_rdata(rdata),.m_axi_rready(rready),.m_axi_rvalid(rvalid),.m_axi_rresp(2'b0),
   .s_axis_aclk(rfclk),.s_axis_valid(1'b0),.s_axis_data(64'b0),.s_axis_last(1'b0),.s_axis_user(1'b0),
   .m_axis_aclk(rfclk),.m_axis_ready(1'b0),
   .fifo_wr_clk(rfclk),.fifo_wr_en(wr_en),.fifo_wr_din(wr_data),.fifo_wr_sync(wr_sync),
   .fifo_wr_overflow(overflow),.fifo_wr_xfer_req(wr_xfer),
   .fifo_rd_clk(rfclk),.fifo_rd_en(rd_en),.fifo_rd_valid(rd_valid),.fifo_rd_dout(rd_data),
   .fifo_rd_underflow(underflow),.fifo_rd_xfer_req(rd_xfer));
 // BFM accepts AW independently of W; W is held until an address is known.
 // Ordered AXI responses with random stalls and bounded recurring long stalls.
 always @(posedge qclk) if(rst) begin
   if(eot)eots=eots+1;
   if(awvalid && awready)begin
     if(awsize!=3 || awburst!=1 || awaddr[2:0]!=0)$fatal(1,"invalid AW geometry case=%0d",ID);
     a_addr[a_tail%1024]=awaddr/8;a_count[a_tail%1024]=awlen[3:0]+1;a_tail=a_tail+1;awbursts=awbursts+1;
   end
   if(wvalid && !wready)wstalls=wstalls+1;
   if(wvalid && wready)begin
     if(a_head>=a_tail)$fatal(1,"W without accepted AW");
     if(wlast!==(a_count[a_head%1024]==1) || wstrb!==8'hff)$fatal(1,"WLAST/strobe error case=%0d",ID);
     if(checking)begin
       if(wdata!==pattern(a_addr[a_head%1024]))$fatal(1,"RX payload error case=%0d at=%0d got=%h want=%h",ID,a_addr[a_head%1024],wdata,pattern(a_addr[a_head%1024]));
       checked=checked+1;received=received+1;
     end
     nwrite=nwrite+1;a_addr[a_head%1024]=a_addr[a_head%1024]+1;a_count[a_head%1024]=a_count[a_head%1024]-1;
     if(wlast)begin a_head=a_head+1;b_pending=b_pending+1;end
   end
   if(bvalid && bready)b_pending=b_pending-1;
   if(arvalid && arready)begin
     if(arsize!=3 || arburst!=1 || araddr[2:0]!=0)$fatal(1,"invalid AR geometry case=%0d",ID);
     r_addr[r_tail%1024]=araddr/8;r_count[r_tail%1024]=arlen[3:0]+1;r_tail=r_tail+1;arbursts=arbursts+1;
   end
   if(rvalid && !rready)rstalls=rstalls+1;
   if(rvalid && rready)begin
     nread=nread+1;r_addr[r_head%1024]=r_addr[r_head%1024]+1;r_count[r_head%1024]=r_count[r_head%1024]-1;
     if(r_count[r_head%1024]==0)r_head=r_head+1;
   end
 end
 reg rheld=0;reg [63:0] oldr=0;
 always @(negedge qclk) begin
   qcycle=qcycle+1;rng={rng[30:0],rng[31]^rng[21]^rng[1]^rng[0]};
   awready=rst && !TX && rng[0] && a_tail-a_head<16;
   wready=rst && !TX && a_head<a_tail && rng[2:1]!=0 && qcycle%97<81;
   bvalid=rst && b_pending>0 && rng[3];
   arready=rst && TX && rng[0] && r_tail-r_head<16;
   if(!rst)begin rvalid=0;rdata=0;end
   else if(!(rvalid && !rready))begin
     rvalid=TX && r_head<r_tail && rng[5:4]!=0 && qcycle%83<71;
     rdata=(r_head<r_tail)?pattern(r_addr[r_head%1024]):0;
   end
 end
 // No internal FIFO ready signal is used to throttle the input. Cadence leaves
 // headroom for this bounded BFM; overflow remains checked explicitly.
 always @(negedge rfclk)begin
   rcycle=rcycle+1;
   wr_en=rst && !TX && produce && wr_xfer && sent<job_size && rcycle%8==0;
   wr_data=pattern(job_base+sent);wr_sync=wr_en;
   rd_en=rst && TX && produce && rd_xfer && rcycle%4==0;
 end
 always @(posedge rfclk)begin
   if(rst && wr_en)sent=sent+1;
   #0.01;
   if(rst && overflow)begin overflows=overflows+1;if(!aborting)$fatal(1,"unexpected FIFO overflow case=%0d",ID);end
   if(rst && underflow)underflows=underflows+1;
   if(rst && TX && rd_valid && checking)begin
     if(received>=job_size || rd_data!==pattern(job_base+received))$fatal(1,"TX payload/stale error case=%0d beat=%0d",ID,received);
     checked=checked+1;received=received+1;
   end
 end
 task automatic request_job(input integer base,input integer beats,input integer early_abort);
   integer before_eot;
   begin
     @(negedge qclk);job_base=base;job_size=beats;sent=0;received=0;
     address=base;length=beats*8-1;sync_start=!TX;checking=1;produce=1;
     before_eot=eots;req_valid=1;
     do @(posedge qclk);while(!req_ready);
     @(negedge qclk);req_valid=0;
     if(!early_abort)begin
       wait(received==beats && eots==before_eot+1);
       repeat(15)@(negedge qclk);produce=0;checking=0;jobs=jobs+1;
     end else begin
       wait(received>=32);
       @(negedge qclk);checking=0;aborting=1;enable=0;produce=0;aborts=aborts+1;
       // AXI outstanding bursts must drain; data of the cancelled request is
       // intentionally not asserted as valid application data after disable.
       wait(!dut.do_enable && !dut.enabled_src && !dut.enabled_dest && dut.fifo_empty &&
         dut.request_id==dut.response_id && !dut.sync_id && a_head==a_tail && r_head==r_tail && b_pending==0);
       repeat(100)@(negedge qclk);aborting=0;enable=1;
       wait(dut.enabled);repeat(10)@(negedge qclk);
     end
   end
 endtask
 integer j,size,epoch;
 initial begin
   repeat(30)@(negedge qclk);rst=1;
   repeat(30)@(negedge qclk);enable=1;wait(dut.enabled);
   for(epoch=0;epoch<2;epoch=epoch+1)begin
     for(j=0;j<32;j=j+1)begin
       case(j%9)0:size=1;1:size=2;2:size=15;3:size=16;4:size=17;5:size=31;6:size=33;7:size=64;8:size=256;endcase
       request_job((epoch*32+j)*1024,size,0);
     end
     if(epoch==0)begin
       @(negedge qclk);enable=0;
       wait(!dut.do_enable && !dut.enabled_src && !dut.enabled_dest && dut.fifo_empty);
       repeat(100)@(negedge qclk);normal_stops=normal_stops+1;enable=1;wait(dut.enabled);
       request_job(100000,4096,1);
     end
   end
   @(negedge qclk);enable=0;produce=0;
   wait(!dut.enabled_src && !dut.enabled_dest && dut.fifo_empty);
   repeat(100)@(negedge qclk);
   if(a_head!=a_tail || r_head!=r_tail || b_pending!=0 || checked==0 || jobs!=64 || aborts!=1)
     $fatal(1,"incomplete final counters case=%0d",ID);
   $display("P32_FIFO_MM_CASE_PASS id=%0d tx=%0d completed_jobs=%0d checked_beats=%0d aborts=%0d drained_restarts=%0d aw=%0d ar=%0d wstalls=%0d rstalls=%0d underflows=%0d overflows=%0d",ID,TX,jobs,checked,aborts,normal_stops,awbursts,arbursts,wstalls,rstalls,underflows,overflows);
   done=1;
 end
endmodule
module tb_p32_dmac_fifo_mm;
 wire [3:0]done;
 p32_case #(.ID(0),.TX(0),.RFHALF(7.1)) a(done[0]);
 p32_case #(.ID(1),.TX(1),.RFHALF(7.1)) b(done[1]);
 p32_case #(.ID(2),.TX(0),.RFHALF(3.7)) c(done[2]);
 p32_case #(.ID(3),.TX(1),.RFHALF(3.7)) d(done[3]);
 initial begin wait(&done);$display("P32_FIFO_MM_TB_PASS cases=4");$finish;end
 initial begin #10000000;$display("P32_TIMEOUT states a=%h b=%h c=%h d=%h",a.dut.dbg_status,b.dut.dbg_status,c.dut.dbg_status,d.dut.dbg_status);$fatal(1,"timeout");end
endmodule
