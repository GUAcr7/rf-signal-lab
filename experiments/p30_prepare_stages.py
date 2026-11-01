"""Prepare full synthesis, structural audit and route-only investigation stages."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def main():
    active=json.loads((ROOT/'results/p30-active-build.json').read_text('utf-8'))
    work=Path(active['work']);project=Path(active['project'])
    prefix=f'''set_param general.maxThreads 2
cd {{{work.as_posix()}}}
open_project {{{project.as_posix()}}}
if {{[get_property PART [current_project]] ne "xc7z100ffg900-2"}} {{error "wrong device"}}
'''
    reports='''report_utilization -file merged-STAGE-utilization.rpt
report_timing_summary -report_unconstrained -file merged-STAGE-timing.rpt
check_timing -verbose -file merged-STAGE-check-timing.rpt
report_drc -file merged-STAGE-drc.rpt
report_cdc -details -file merged-STAGE-cdc.rpt
report_clocks -file merged-STAGE-clocks.rpt
report_clock_interaction -file merged-STAGE-clock-interaction.rpt
report_bus_skew -warn_on_violation -file merged-STAGE-bus-skew.rpt
report_methodology -file merged-STAGE-methodology.rpt
report_io -file merged-STAGE-io.rpt
write_checkpoint -force merged-STAGE.dcp
'''
    clock_guard=r'''
set div_c [get_pins -hier -filter {NAME =~ */dual_pixel_24bpp_lvds_mapping_0/inst/parity_flag_reg/C}]
set div_q [get_pins -hier -filter {NAME =~ */dual_pixel_24bpp_lvds_mapping_0/inst/parity_flag_reg/Q}]
if {[llength $div_c] != 1 || [llength $div_q] != 1} {error "divider hierarchy is ambiguous or missing"}
set master [get_clocks -of_objects $div_c]
set derived [get_clocks -of_objects $div_q]
if {[llength $master] != 1 || [llength $derived] != 1 || $derived ne "p29_lvds_half_pclk"} {error "clock model missing or ambiguous"}
set master_period [get_property PERIOD $master]
set derived_period [get_property PERIOD $derived]
if {abs($derived_period-2.0*$master_period) > 0.000001} {error "clock divider ratio changed"}
if {[llength [get_clocks -quiet *clk_wiz_0/inst/clk_in1]] != 0} {error "ClockWiz incorrectly redefines the internal PS FCLK"}
puts "P30_CLOCK_GUARD_PASS master_ns=$master_period divided_ns=$derived_period"
'''
    synth=prefix+'''generate_target all [get_files *.bd]
update_compile_order -fileset sources_1
if {[get_property PROGRESS [get_runs synth_1]] eq "100%"} {reset_run synth_1}
launch_runs synth_1 -jobs 2
wait_on_run synth_1
set status [get_property STATUS [get_runs synth_1]]
puts "P30_SYNTH_STATUS $status"
if {[get_property PROGRESS [get_runs synth_1]] ne "100%" || ![string match *Complete* $status]} {exit 40}
open_run synth_1
set blackboxes [get_cells -quiet -hier -filter {IS_BLACKBOX == 1}]
if {[llength $blackboxes]} {error "unresolved modules: $blackboxes"}
'''+clock_guard+reports.replace('STAGE','synth')+'''puts "P30_MERGED_SYNTH_PASS"
close_project
exit 0
'''
    (work/'synth.tcl').write_text(synth,encoding='utf-8',newline='\n')
    implement=prefix+'''if {[get_property PROGRESS [get_runs synth_1]] ne "100%"} {error "synthesis not complete"}
launch_runs impl_1 -to_step route_design -jobs 2
wait_on_run impl_1
set status [get_property STATUS [get_runs impl_1]]
puts "P30_IMPLEMENT_STATUS $status"
if {![string match *route_design*Complete* $status]} {exit 41}
open_run impl_1
'''+clock_guard+reports.replace('STAGE','route')+'''report_route_status -file merged-route-status.rpt
# A routed checkpoint is evidence for timing/placement investigation only.
# No write_bitstream, export_hardware, boot image, FPGA programming or board I/O.
puts "P30_IMPLEMENT_COMPLETED"
close_project
exit 0
'''
    (work/'implement.tcl').write_text(implement,encoding='utf-8',newline='\n')
    audit=prefix+r'''
open_bd_design [get_files *.bd]
proc same_net {objects expected} {
    set nets {}
    foreach obj $objects {
        set n [get_bd_nets -quiet -of_objects [get_bd_pins $obj]]
        if {[llength $n] != 1} {error "expected connected pin $obj"}
        lappend nets $n
    }
    if {[llength [lsort -unique $nets]] != 1} {error "net mismatch $objects: $nets"}
    puts "P30_NET_VERIFIED $expected $nets"
}
foreach i {0 1 2 3} {
    same_net [list sys_ps7/FCLK_CLK1 axi_cpu_interconnect/M0${i}_ACLK] display_axi_200m
    same_net [list rst_ps7_0_200M/peripheral_aresetn axi_cpu_interconnect/M0${i}_ARESETN] display_axi_reset_200m
}
same_net {sys_ps7/FCLK_CLK0 sys_ps7/M_AXI_GP0_ACLK axi_ad9361/s_axi_aclk axi_ad9361_adc_dma/m_dest_axi_aclk axi_ad9361_dac_dma/m_src_axi_aclk sys_ps7/S_AXI_HP1_ACLK sys_ps7/S_AXI_HP2_ACLK} RF_CPU_100m
same_net {sys_ps7/FCLK_CLK1 sys_ps7/S_AXI_HP0_ACLK smartconnect_0/aclk axi_vdma_0/m_axi_mm2s_aclk axi_vdma_0/m_axi_s2mm_aclk} VIDEO_DDR_200m
foreach {source index} {axi_vdma_0/mm2s_introut 0 axi_vdma_0/s2mm_introut 1 v_tc_0/irq 2 v_tpg_0/interrupt 3 axi_ad9361_dac_dma/irq 12 axi_ad9361_adc_dma/irq 13} {
    same_net [list $source sys_concat_intc/In$index] IRQ_In$index
}
foreach pin {sys_ps7/SPI0_SS_I sys_ps7/SPI0_SCLK_I sys_ps7/SPI0_MOSI_I} {
    set net [get_bd_nets -of_objects [get_bd_pins $pin]]
    puts "P30_SPI_INPUT $pin $net"
}
set f [open merged-ps-config.txt w]
foreach prop [lsort [list_property [get_bd_cells sys_ps7]]] {
    if {[string match CONFIG.* $prop]} {puts $f [list $prop [get_property $prop [get_bd_cells sys_ps7]]]}
}
close $f
set f [open merged-pin-net-map.txt w]
foreach pin [lsort [get_bd_pins -hier]] {
    set nets [get_bd_nets -quiet -of_objects $pin]
    puts $f [list $pin [get_property DIR $pin] $nets]
}
close $f
set f [open merged-address.rpt w]
foreach segment [lsort [get_bd_addr_segs -hier]] {
    set row [list $segment]
    foreach prop {OFFSET RANGE} {
        if {$prop in [list_property $segment]} {lappend row $prop [get_property $prop $segment]}
    }
    puts $f $row
}
close $f
validate_bd_design
puts "P30_AUDIT_PASS"
close_project
exit 0
'''
    (work/'audit.tcl').write_text(audit,encoding='utf-8',newline='\n')
    print(work)


if __name__=='__main__':main()
