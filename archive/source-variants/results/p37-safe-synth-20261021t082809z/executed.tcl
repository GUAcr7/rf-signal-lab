set_param general.maxThreads 2
cd {E:/p37-clock-082321}
open_project {E:/p37-clock-082321/project/combined.xpr}
if {[get_property PART [current_project]] ne "xc7z100ffg900-2"} {error "wrong device"}
generate_target all [get_files *.bd]
update_compile_order -fileset sources_1
if {[get_property PROGRESS [get_runs synth_1]] eq "100%"} {reset_run synth_1}
launch_runs synth_1 -jobs 2
wait_on_run synth_1
set status [get_property STATUS [get_runs synth_1]]
puts "P37_SYNTH_STATUS $status"
if {[get_property PROGRESS [get_runs synth_1]] ne "100%" || ![string match *Complete* $status]} {exit 40}
open_run synth_1

set blackboxes [get_cells -quiet -hier -filter {IS_BLACKBOX == 1}]
if {[llength $blackboxes]} {error "unresolved cells $blackboxes"}
set auxiliary [get_cells -quiet -hier -filter {NAME =~ *lvds_n_x_7to1* || NAME =~ *dual_pixel* || NAME =~ *parity_flag* || REF_NAME =~ PLLE2*}]
if {[llength $auxiliary]} {error "unused LVDS/PLL remains $auxiliary"}
if {[llength [get_ports -quiet lvds_*]] || [llength [get_ports -quiet o_video*]]} {error "unused external port remains"}
proc single_clock {obj expected label} {
  if {[llength $obj]!=1} {error "$label object count [llength $obj]"}
  set clock [get_clocks -quiet -of_objects $obj]
  if {[llength $clock]!=1} {error "$label clock count [llength $clock]: $clock"}
  set period [get_property PERIOD $clock]
  if {abs($period-$expected)>0.002} {error "$label period $period != $expected"}
  puts "P37_CLOCK $label $clock period_ns=$period"
  return $clock
}
set ps [get_cells -hier -filter {REF_NAME == PS7}]
if {[llength $ps]!=1} {error "PS7 count [llength $ps]"}
set fclk0 {}; set fclk1 {}
foreach p [get_pins -of_objects $ps] {
  set rn [get_property REF_PIN_NAME $p]
  if {$rn eq {FCLKCLK[0]}} {set fclk0 $p}
  if {$rn eq {FCLKCLK[1]}} {set fclk1 $p}
}
set ps100 [single_clock $fclk0 10.0 ps_fclk0]
set ps200 [single_clock $fclk1 5.0 ps_fclk1]
set pixel [single_clock [get_ports lcd_pclk] [expr {1000.0/33.0}] lcd_pixel]
if {![get_property IS_GENERATED $pixel]} {error "LCD clock is not generated"}
set clk_input [get_pins -quiet -hier -filter {NAME =~ */clk_wiz_0/*/mmcm_adv_inst/CLKIN1}]
set wiz100 [single_clock $clk_input 10.0 clockwiz_input]
if {$wiz100 ne $ps100} {error "ClockWiz input creates a new clock instead of inherited FCLK0"}
set axi_pin [get_pins -quiet -hier -filter {NAME =~ */clk_wiz_0/s_axi_aclk}]
set wiz200 [single_clock $axi_pin 5.0 clockwiz_axi]
if {$wiz200 ne $ps200} {error "ClockWiz AXI does not inherit FCLK1"}
if {[llength [get_clocks -quiet *clk_wiz_0/inst/clk_in1]]} {error "internal ClockWiz create_clock remains"}
puts "P37_TTL_CLOCK_GUARD_PASS no_auxiliary_lvds single_pixel_33MHz"

set m [get_cells -quiet -hier -filter {REF_NAME == MMCME2_ADV && NAME =~ *clk_wiz_0*}]
if {[llength $m]!=1} {error "safe MMCM instance ambiguous"}
foreach {key wanted} {CLKFBOUT_MULT_F 16.5 DIVCLK_DIVIDE 2 CLKOUT0_DIVIDE_F 25} {
 set actual [get_property $key $m]
 if {abs($actual-$wanted)>0.0001} {error "unsafe MMCM $key $actual"}
 puts "P37_MMCM $key=$actual"
}
puts "P37_SAFE_MMCM_PRIMITIVE_PASS"
report_utilization -file {C:/Users/project_user/Documents/Codex/2026-09-09/2026-fpga-fmql30tai-fpai-python-c/outputs/rf-signal-lab/results/p37-safe-synth-20261021T082809Z/utilization.rpt}
report_timing_summary -report_unconstrained -file {C:/Users/project_user/Documents/Codex/2026-09-09/2026-fpga-fmql30tai-fpai-python-c/outputs/rf-signal-lab/results/p37-safe-synth-20261021T082809Z/timing.rpt}
check_timing -verbose -file {C:/Users/project_user/Documents/Codex/2026-09-09/2026-fpga-fmql30tai-fpai-python-c/outputs/rf-signal-lab/results/p37-safe-synth-20261021T082809Z/check-timing.rpt}
report_drc -file {C:/Users/project_user/Documents/Codex/2026-09-09/2026-fpga-fmql30tai-fpai-python-c/outputs/rf-signal-lab/results/p37-safe-synth-20261021T082809Z/drc.rpt}
report_cdc -details -file {C:/Users/project_user/Documents/Codex/2026-09-09/2026-fpga-fmql30tai-fpai-python-c/outputs/rf-signal-lab/results/p37-safe-synth-20261021T082809Z/cdc.rpt}
report_clocks -file {C:/Users/project_user/Documents/Codex/2026-09-09/2026-fpga-fmql30tai-fpai-python-c/outputs/rf-signal-lab/results/p37-safe-synth-20261021T082809Z/clocks.rpt}
report_clock_interaction -file {C:/Users/project_user/Documents/Codex/2026-09-09/2026-fpga-fmql30tai-fpai-python-c/outputs/rf-signal-lab/results/p37-safe-synth-20261021T082809Z/clock-interaction.rpt}
report_bus_skew -warn_on_violation -file {C:/Users/project_user/Documents/Codex/2026-09-09/2026-fpga-fmql30tai-fpai-python-c/outputs/rf-signal-lab/results/p37-safe-synth-20261021T082809Z/bus-skew.rpt}
report_methodology -file {C:/Users/project_user/Documents/Codex/2026-09-09/2026-fpga-fmql30tai-fpai-python-c/outputs/rf-signal-lab/results/p37-safe-synth-20261021T082809Z/methodology.rpt}
report_io -file {C:/Users/project_user/Documents/Codex/2026-09-09/2026-fpga-fmql30tai-fpai-python-c/outputs/rf-signal-lab/results/p37-safe-synth-20261021T082809Z/io.rpt}
write_checkpoint -force {E:/p37-clock-082321/p37-safe-synth.dcp}
puts "P37_TTL_SYNTH_PASS"
close_project
exit 0
