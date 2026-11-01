set_param general.maxThreads 2
puts "P29_PACKAGING_MIGRATION tool=[version -short] original_ADI_expected=2017.4.1"
set library {E:/FPGA_Tools/Work/p29-vendor-20261019T082112Z/adi/library}
foreach name {axi_ad9361 util_cdc util_axis_fifo util_axis_resize axi_dmac util_clkdiv util_cpack util_rfifo util_tdd_sync util_upack util_wfifo} {
    puts "P29_PACKAGE_BEGIN $name"
    cd [file join $library $name]
    if {[catch {source ${name}_ip.tcl} reason opts]} {
        puts "P29_PACKAGE_FAILED $name $reason"
        puts [dict get $opts -errorinfo]
        exit 10
    }
    if {![file exists component.xml]} {puts "P29_COMPONENT_MISSING $name"; exit 11}
    puts "P29_PACKAGE_PASS $name"
    close_project
}
puts "P29_ALL_IPS_PACKAGED"
exit 0
