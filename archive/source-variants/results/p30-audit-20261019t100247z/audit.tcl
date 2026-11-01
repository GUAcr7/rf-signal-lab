set_param general.maxThreads 2
cd {E:/p30c-1019-174235}
open_project {E:/p30c-1019-174235/project/combined.xpr}
if {[get_property PART [current_project]] ne "xc7z100ffg900-2"} {error "wrong device"}

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
