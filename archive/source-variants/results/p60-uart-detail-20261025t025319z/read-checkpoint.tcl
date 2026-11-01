set_param general.maxThreads 2
open_checkpoint {C:/Users/project_user/Documents/Codex/2026-09-09/2026-fpga-fmql30tai-fpai-python-c/outputs/rf-signal-lab/results/p201-uart-route-20261024T024517Z/uart-routed.dcp}
report_cdc -details -file {C:/Users/project_user/Documents/Codex/2026-09-09/2026-fpga-fmql30tai-fpai-python-c/outputs/rf-signal-lab/results/p60-uart-detail-20261025T025319Z/cdc-details.rpt}
check_timing -verbose -file {C:/Users/project_user/Documents/Codex/2026-09-09/2026-fpga-fmql30tai-fpai-python-c/outputs/rf-signal-lab/results/p60-uart-detail-20261025T025319Z/check-timing.rpt}
report_clocks -file {C:/Users/project_user/Documents/Codex/2026-09-09/2026-fpga-fmql30tai-fpai-python-c/outputs/rf-signal-lab/results/p60-uart-detail-20261025T025319Z/clocks.rpt}
set f [open {C:/Users/project_user/Documents/Codex/2026-09-09/2026-fpga-fmql30tai-fpai-python-c/outputs/rf-signal-lab/results/p60-uart-detail-20261025T025319Z/UART-properties.txt} w]
foreach p {ext_uart_tx ext_uart_rx} {
  puts $f "$p pin=[get_property PACKAGE_PIN [get_ports $p]] io=[get_property IOSTANDARD [get_ports $p]]"
}
close $f
puts "P60_READ_ONLY_CHECKPOINT_REPORTS_DONE"
close_design
