set_param general.maxThreads 2
open_project {E:/p37-clock-082321/project/combined.xpr}
if {[get_property PART [current_project]] ne "xc7z100ffg900-2"} {error "wrong part"}
open_bd_design [get_files */system.bd]
set wiz [get_bd_cells clk_wiz_0]
set_property -dict [list CONFIG.OVERRIDE_MMCM {true} CONFIG.MMCM_DIVCLK_DIVIDE {2} CONFIG.MMCM_CLKFBOUT_MULT_F {16.500} CONFIG.MMCM_CLKOUT0_DIVIDE_F {25.000}] $wiz
validate_bd_design
save_bd_design
foreach {key expected} {OVERRIDE_MMCM true MMCM_DIVCLK_DIVIDE 2 MMCM_CLKFBOUT_MULT_F 16.500 MMCM_CLKOUT0_DIVIDE_F 25.000} {
  set actual [get_property CONFIG.$key $wiz]
  puts "P37_CONFIG $key=$actual"
  if {$key eq "OVERRIDE_MMCM"} {if {$actual ne $expected} {error "override not kept"}} else {if {abs($actual-$expected)>0.0001} {error "MMCM setting not kept"}}
}
generate_target all [get_files *.bd]
write_bd_tcl -force {E:/p37-clock-082321/p37-safe-clock-validated.tcl}
puts "P37_SAFE_CLOCK_GENERATED"
close_project
exit 0
