module preflight_tb;
  reg clk = 0;
  integer edges = 0;
  always #5 clk = ~clk;
  always @(posedge clk) edges = edges + 1;
  initial begin
    #101;
    if (edges != 10) $fatal(1, "clock check failed: %0d", edges);
    $display("PASS: Icarus compile and simulation, 10 clock edges");
    $finish;
  end
endmodule
