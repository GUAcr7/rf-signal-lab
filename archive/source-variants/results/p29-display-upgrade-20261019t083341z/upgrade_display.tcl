set_param general.maxThreads 2
cd {E:/FPGA_Tools/Work/p29-vendor-20261019T082112Z}
open_project {E:/FPGA_Tools/Work/p29-vendor-20261019T082112Z/display-v2/axi_video_display.xpr}
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
set f [open display-config-delta.txt w]
set critical 0
foreach key [lsort -unique [concat [dict keys $before] [dict keys $after]]] {
    set a <ABSENT>; set b <ABSENT>
    if {[dict exists $before $key]} {set a [dict get $before $key]}
    if {[dict exists $after $key]} {set b [dict get $after $key]}
    if {$a ne $b} {
        puts $f [list $key $a $b]
        if {[lindex $key 0] ne "cell" || [string match */processing_system7_0* [lindex $key 1]]} {
            incr critical
        }
    }
}
close $f
report_ip_status -file display-upgraded-ip-status.rpt
write_bd_tcl -force display-migrated-bd.tcl
puts "P29_DISPLAY_CONFIG_CRITICAL_DELTA $critical"
set locked [get_ips -quiet -filter {IS_LOCKED == 1}]
if {[llength $locked]} {puts "P29_DISPLAY_LOCKED $locked"; exit 31}
if {$critical != 0} {puts "P29_DISPLAY_REVIEW_REQUIRED"; exit 32}
puts "P29_DISPLAY_BD_VALIDATED cells=[llength [get_bd_cells -hier]]"
close_project
exit 0
