set_param general.maxThreads 2
cd {E:/FPGA_Tools/Work/p29-vendor-20261019T082112Z}
foreach mode {rf display} {
    open_checkpoint ${mode}-synth.dcp
    report_clocks -file ${mode}-compiled-clocks.rpt
    report_clock_interaction -file ${mode}-compiled-clock-interaction.rpt
    report_cdc -details -file ${mode}-compiled-cdc.rpt
    report_drc -file ${mode}-compiled-drc.rpt
    report_io -file ${mode}-compiled-io.rpt
    close_design
}
puts "P29_COMPILED_REPORTS_WRITTEN"
exit 0
