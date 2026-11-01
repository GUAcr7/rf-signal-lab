# Enumerate a localhost hardware server. Never program, reset, refresh probes,
# halt processors, read/write address space, or touch an existing bitstream.
if {[catch {
  open_hw_manager
  connect_hw_server -url 127.0.0.1:3121
  set targets [get_hw_targets -quiet]
  set handle [open targets.txt w]
  puts $handle "Target count: [llength $targets]"
  foreach target $targets { puts $handle "Target: $target" }
  puts $handle "No target opened; device ID/board model remains unverified by JTAG."
  close $handle
  disconnect_hw_server
  close_hw_manager
  puts "P06_JTAG_DISCOVERY_COMPLETE count=[llength $targets]"
} problem options]} {
  puts stderr "P06_JTAG_DISCOVERY_FAILED $problem"
  if {[dict exists $options -errorinfo]} { puts stderr [dict get $options -errorinfo] }
  exit 1
}
exit 0
