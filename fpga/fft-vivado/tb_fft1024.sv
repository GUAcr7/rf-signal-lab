`timescale 1ns/1ps
// Self-checking installed FFT IP. No board pins, RF controls or bitstream.
module tb_fft1024;
  localparam N=1024, FRAMES=11;
  reg aclk=0;
  always #5 aclk=~aclk;
  reg aresetn=0;
  reg [7:0] config_data=8'h01; // forward FFT, no scaling schedule
  reg config_valid=0;
  wire config_ready;
  reg [31:0] input_data=0;
  reg input_valid=0,input_last=0;
  wire input_ready;
  wire [63:0] output_data;
  wire [15:0] output_user;
  wire output_valid,output_last;
  reg output_ready=0;
  wire frame_started,tlast_unexpected,tlast_missing,status_halt,input_halt,output_halt;
  reg [31:0] input_words[0:N*FRAMES-1];
  reg [63:0] expected_words[0:N*FRAMES-1];
  string inputs_path,expected_path,trace_path,metrics_path;
  integer cycles=0,epoch=0,output_count=0,completed_frames=0,total_checked=0;
  integer input_stall_cycles=0,output_stall_cycles=0,first_input_cycle=-1;
  integer first_output_cycle=-1,last_input_cycle=-1,last_output_cycle=-1;
  integer trace_file,metrics_file;
  integer stalls=1;
  integer accepted_inputs=0;
  integer input_first[0:FRAMES-1],input_end[0:FRAMES-1];
  reg held_output=0;
  reg [80:0] held_payload;

  fft1024_0 dut(
    .aclk(aclk),.aresetn(aresetn),
    .s_axis_config_tdata(config_data),.s_axis_config_tvalid(config_valid),.s_axis_config_tready(config_ready),
    .s_axis_data_tdata(input_data),.s_axis_data_tvalid(input_valid),
    .s_axis_data_tready(input_ready),.s_axis_data_tlast(input_last),
    .m_axis_data_tdata(output_data),.m_axis_data_tuser(output_user),
    .m_axis_data_tvalid(output_valid),.m_axis_data_tready(output_ready),.m_axis_data_tlast(output_last),
    .event_frame_started(frame_started),.event_tlast_unexpected(tlast_unexpected),
    .event_tlast_missing(tlast_missing),.event_status_channel_halt(status_halt),
    .event_data_in_channel_halt(input_halt),.event_data_out_channel_halt(output_halt));

  always @(negedge aclk) begin
    output_ready = aresetn && (!stalls || cycles%11<7); // deterministic downstream stalls
  end
  always @(posedge aclk) begin
    cycles=cycles+1;
    if(cycles>1000000) $fatal(1,"FFT_TIMEOUT");
    if(!aresetn) begin
      output_count=0; completed_frames=0; held_output=0;
      first_input_cycle=-1; first_output_cycle=-1;
      last_input_cycle=-1; last_output_cycle=-1;
      accepted_inputs=0;
    end else begin
      if(tlast_missing || tlast_unexpected) $fatal(1,"FFT_TLAST_EVENT");
      if(input_valid && !input_ready) input_stall_cycles=input_stall_cycles+1;
      if(output_valid && !output_ready) output_stall_cycles=output_stall_cycles+1;
      if(input_valid && input_ready) begin
        if(accepted_inputs>=FRAMES*N) $fatal(1,"FFT_EXTRA_INPUT");
        if(accepted_inputs%N==0) input_first[accepted_inputs/N]=cycles;
        input_end[accepted_inputs/N]=cycles;
        accepted_inputs=accepted_inputs+1;
        if(first_input_cycle<0) first_input_cycle=cycles;
        last_input_cycle=cycles;
      end
      if(held_output && (!output_valid || {output_last,output_user,output_data}!==held_payload))
        $fatal(1,"FFT_OUTPUT_CHANGED_WHILE_STALLED");
      held_output=output_valid && !output_ready;
      held_payload={output_last,output_user,output_data};
      if(output_valid && output_ready) begin
        if(epoch==0) $fatal(1,"FFT_LEAKED_ABORTED_FRAME");
        if(output_count>=FRAMES*N) $fatal(1,"FFT_EXTRA_OUTPUT");
        if(first_output_cycle<0) first_output_cycle=cycles;
        last_output_cycle=cycles;
        if(output_user[9:0] !== (output_count%N))
          $fatal(1,"FFT_WRONG_NATURAL_INDEX expected=%0d actual=%0d",output_count%N,output_user[9:0]);
        if(output_last !== (output_count%N==N-1)) $fatal(1,"FFT_WRONG_OUTPUT_TLAST");
        if(output_data[26:0] !== expected_words[output_count][26:0] ||
           output_data[58:32] !== expected_words[output_count][58:32])
          $fatal(1,"FFT_VALUE_MISMATCH epoch=%0d item=%0d expected=%h actual=%h",epoch,output_count,expected_words[output_count],output_data);
        $fwrite(trace_file,"%0d,%0d,%0d,%0d,%0d,%0d\n",epoch,output_count/N,output_count%N,
                $signed(output_data[26:0]),$signed(output_data[58:32]),cycles);
        total_checked=total_checked+1;
        output_count=output_count+1;
        if(output_count%N==0) begin
          completed_frames=completed_frames+1;
          $fwrite(metrics_file,"%0d,%0d,%0d,%0d,%0d,%0d\n",epoch,completed_frames-1,
                  input_first[completed_frames-1],input_end[completed_frames-1],first_output_cycle,last_output_cycle);
          first_input_cycle=-1;first_output_cycle=-1;
        end
      end
    end
  end

  task reset_core;
    begin
      @(negedge aclk); aresetn=0;input_valid=0;input_last=0;config_valid=0;
      repeat(20) @(negedge aclk);
      aresetn=1;
      repeat(5) @(negedge aclk);
      config_valid=1;
      @(posedge aclk);
      while(!config_ready) @(posedge aclk);
      @(negedge aclk);config_valid=0;
    end
  endtask
  task send_word(input integer address,input integer last_flag);
    begin
      // Drive only on falling edge; hold valid/payload until an accepted beat.
      if(stalls && address%7==3) begin
        @(negedge aclk);input_valid=0;input_last=0;
        repeat(2) @(negedge aclk);
      end
      @(negedge aclk);
      input_data=input_words[address];input_valid=1;input_last=last_flag;
      @(posedge aclk);
      while(!input_ready) @(posedge aclk);
      if(stalls) begin
        @(negedge aclk);input_valid=0;input_last=0;
      end
    end
  endtask

  integer frame,index;
  initial begin
    if($value$plusargs("STALLS=%d",stalls)) begin end
    if(!$value$plusargs("INPUTS=%s",inputs_path) || !$value$plusargs("EXPECTED=%s",expected_path) ||
       !$value$plusargs("TRACE=%s",trace_path) || !$value$plusargs("METRICS=%s",metrics_path))
      $fatal(1,"FFT_MISSING_VECTOR_PATHS");
    $readmemh(inputs_path,input_words);
    $readmemh(expected_path,expected_words);
    trace_file=$fopen(trace_path,"w");metrics_file=$fopen(metrics_path,"w");
    if(!trace_file || !metrics_file) $fatal(1,"FFT_CANNOT_OPEN_EVIDENCE");
    $fwrite(trace_file,"epoch,frame,bin,real_counts,imag_counts,cycle\n");
    $fwrite(metrics_file,"epoch,frame,first_input_cycle,last_input_cycle,first_output_cycle,last_output_cycle\n");
    reset_core();
    for(index=0;index<37;index=index+1) send_word(index,0);
    reset_core(); // discard partial frame, must not contaminate next epoch
    for(epoch=1;epoch<=2;epoch=epoch+1) begin
      if(epoch==2) reset_core();
      for(frame=0;frame<FRAMES;frame=frame+1) begin
        for(index=0;index<N;index=index+1) send_word(frame*N+index,index==N-1);
        @(negedge aclk);input_valid=0;input_last=0;
        if(stalls) begin
          wait(completed_frames==frame+1);
          repeat(10) @(negedge aclk);
        end
      end
      wait(completed_frames==FRAMES);
    end
    repeat(100) @(negedge aclk);
    if(total_checked!=2*FRAMES*N || (stalls && output_stall_cycles==0))
      $fatal(1,"FFT_INCOMPLETE_CHECKS");
    $fclose(trace_file);$fclose(metrics_file);
    $display("P07_FFT_SELF_CHECK_PASS samples=%0d frames=%0d input_stalls=%0d output_stalls=%0d cycles=%0d",
             total_checked,2*FRAMES,input_stall_cycles,output_stall_cycles,cycles);
    $finish;
  end
endmodule
