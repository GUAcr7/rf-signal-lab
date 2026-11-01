set_param general.maxThreads 2
cd {E:/FPGA_Tools/Work/p29-vendor-20261019T082112Z}
open_project {E:/FPGA_Tools/Work/p29-vendor-20261019T082112Z/display-v3/axi_video_display.xpr}
open_bd_design [get_files */axi_video_display.bd]
proc snapshot {filename} {
    set data [dict create]
    foreach cell [lsort [get_bd_cells -hier]] {
        foreach prop [lsort [list_property $cell]] {
            if {[string match CONFIG.* $prop] || $prop eq "VLNV"} {
                dict set data [list cell $cell $prop] [get_property $prop $cell]
            }
        }
    }
    foreach kind {port intf_port addr_seg} {
        if {$kind eq "port"} {set objects [get_bd_ports]}
        if {$kind eq "intf_port"} {set objects [get_bd_intf_ports]}
        if {$kind eq "addr_seg"} {set objects [get_bd_addr_segs -hier]}
        foreach obj [lsort $objects] {
            foreach prop [lsort [list_property $obj]] {
                if {[string match CONFIG.* $prop] || $prop in {DIR TYPE LEFT RIGHT VLNV OFFSET RANGE}} {
                    dict set data [list $kind $obj $prop] [get_property $prop $obj]
                }
            }
        }
    }
    set f [open $filename w]
    dict for {key value} $data {puts $f [list $key $value]}
    close $f
    return $data
}
set before [snapshot display-config-before.txt]
set cells {}
foreach cell [get_bd_cells] {
    # Hierarchical Xilinx IP must be upgraded through its root cell, not through
    # the generated xbar/protocol-converter children. Module references stay put.
    if {[string match xilinx.com:ip:* [get_property VLNV $cell]]} {lappend cells $cell}
}
puts "P29_DISPLAY_UPGRADE_CELLS $cells"
upgrade_bd_cells $cells
validate_bd_design
save_bd_design
set after [snapshot display-config-after.txt]
# Reviewed metadata-only deltas from the retained v2 attempt. These are exact
# pairs, not a blanket exception: PS7 slave mappings/configuration must stay put.
set reviewed [dict create]
foreach {port left} {DDR_addr 14 DDR_ba 2 DDR_dm 3 DDR_dq 31 DDR_dqs_n 3 DDR_dqs_p 3 FIXED_IO_mio 53} {
    dict set reviewed [list port /$port LEFT] [list {} $left]
    dict set reviewed [list port /$port RIGHT] [list {} 0]
}
foreach port {lcd_pclk o_video_pclk} {
    dict set reviewed [list port /$port CONFIG.CLK_DOMAIN] [list <ABSENT> /clk_wiz_0_clk_out1]
    dict set reviewed [list port /$port CONFIG.FREQ_HZ] [list <ABSENT> 148500000]
    dict set reviewed [list port /$port CONFIG.PHASE] [list <ABSENT> 0.0]
}
dict set reviewed [list addr_seg /ps7_0_axi_periph/s00_couplers/auto_pc/S_AXI/Reg OFFSET] [list {} <ABSENT>]
dict set reviewed [list addr_seg /ps7_0_axi_periph/s00_couplers/auto_pc/S_AXI/Reg RANGE] [list 0x00010000 <ABSENT>]
set f [open display-config-delta.txt w]
set critical 0
set reviewed_seen 0
foreach key [lsort -unique [concat [dict keys $before] [dict keys $after]]] {
    set a <ABSENT>; set b <ABSENT>
    if {[dict exists $before $key]} {set a [dict get $before $key]}
    if {[dict exists $after $key]} {set b [dict get $after $key]}
    if {$a ne $b} {
        puts $f [list $key $a $b]
        if {[lindex $key 0] ne "cell" || [string match */processing_system7_0* [lindex $key 1]]} {
            if {[dict exists $reviewed $key] && [dict get $reviewed $key] eq [list $a $b]} {
                incr reviewed_seen
            } else {incr critical}
        }
    }
}
close $f
report_ip_status -file display-upgraded-ip-status.rpt
write_bd_tcl -force display-migrated-bd.tcl
puts "P29_DISPLAY_CONFIG_CRITICAL_DELTA $critical"
puts "P29_DISPLAY_REVIEWED_METADATA_DELTA $reviewed_seen"
set locked [get_ips -quiet -filter {IS_LOCKED == 1}]
if {[llength $locked]} {puts "P29_DISPLAY_LOCKED $locked"; exit 31}
if {$critical != 0} {puts "P29_DISPLAY_REVIEW_REQUIRED"; exit 32}
if {$reviewed_seen != 22} {puts "P29_DISPLAY_E:/FPGA_Tools/Work/p29-vendor-20261019T082112ZLINE_CHANGED"; exit 33}
puts "P29_DISPLAY_FUNCTIONAL_MIGRATION_PENDING VTC_default_parameters_and_new_IP_ports_require_simulation_or_hardware_check"
puts "P29_DISPLAY_BD_VALIDATED cells=[llength [get_bd_cells -hier]]"
close_project
exit 0
