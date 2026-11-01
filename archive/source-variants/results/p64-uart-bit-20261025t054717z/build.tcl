set_param general.maxThreads 2
open_checkpoint {C:/Users/project_user/Documents/Codex/2026-09-09/2026-fpga-fmql30tai-fpai-python-c/outputs/rf-signal-lab/results/p201-uart-route-20261024T024517Z/uart-routed.dcp}
foreach {port pin} {ext_uart_tx E17 ext_uart_rx E18} {
 if {[get_property PACKAGE_PIN [get_ports $port]] ne $pin} {error "UART wrong pad"}
 if {[get_property IOSTANDARD [get_ports $port]] ne "LVCMOS33"} {error "UART IO voltage"}
}
set errors [get_drc_violations -quiet -filter {SEVERITY == Error}]
if {[llength $errors]} {error "Existing error DRC"}
write_bitstream -force -bin_file {C:/Users/project_user/Documents/Codex/2026-09-09/2026-fpga-fmql30tai-fpai-python-c/outputs/rf-signal-lab/results/p64-uart-bit-20261025T054717Z/uart-experiment.bit}
puts "P64_UART_OFFLINE_BITSTREAM_DONE_NOT_RELEASE"
close_design
