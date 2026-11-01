# Read the chip identity through the single previously enumerated P201 cable.
# No program_hw_devices, reset, memory read/write, CPU halt or probe refresh.
if {[catch {
  open_hw_manager
  connect_hw_server -url 127.0.0.1:3121
  set targets [get_hw_targets -quiet]
  set expected "127.0.0.1:3121/xilinx_tcf/Digilent/210203859289A"
  if {[llength $targets] != 1 || [lindex $targets 0] ne $expected} { error "Cable identity/count changed; refusing to open another target" }
  set target [lindex $targets 0]
  open_hw_target $target
  set handle [open device-identity.txt w]
  puts $handle "Cable: $target"
  set zynq_found 0
  foreach device [get_hw_devices -quiet] {
    puts $handle "Device: $device"
    set names [list_property $device]
    foreach prop {NAME PART IDCODE JTAG_DEVICE_ID} {
      if {$prop in $names} { puts $handle "$prop: [get_property $prop $device]" }
    }
    if {"PART" in $names && [string match "xc7z020*" [get_property PART $device]]} { set zynq_found 1 }
  }
  puts $handle "Programming/reset/halt/register access: none"
  puts $handle "Package and speed grade are NOT established by this identity scan."
  close $handle
  close_hw_target $target
  disconnect_hw_server
  close_hw_manager
  if {!$zynq_found} { error "Expected xc7z020 family was not identified" }
  puts "P06_JTAG_CHIP_IDENTITY_PASS xc7z020; no programming"
} problem options]} {
  puts stderr "P06_JTAG_IDENTITY_FAILED $problem"
  if {[dict exists $options -errorinfo]} { puts stderr [dict get $options -errorinfo] }
  exit 1
}
exit 0
