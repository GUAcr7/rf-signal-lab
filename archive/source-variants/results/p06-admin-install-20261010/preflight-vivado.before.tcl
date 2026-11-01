# Preparation artifact: execute only after the matching Vivado installation exists.
if {[version -short] ne "2021.1"} {
  error "P06 requires exactly Vivado 2021.1; do not bypass the original version check"
}
set part "xc7z020clg400-2"
if {[llength [get_parts -quiet $part]] != 1} {
  error "Required Zynq-7000 device is unavailable: $part"
}
puts "P06_TOOL_VERSION [version -short]"
puts "P06_REQUIRED_PART $part"
foreach ip {processing_system7 axi_interconnect axi_quad_spi axi_iic proc_sys_reset xlconcat xlslice util_vector_logic fir_compiler} {
  set definitions [get_ipdefs -all -filter "VLNV =~ xilinx.com:ip:${ip}:* && design_tool_contexts =~ *IPI* && UPGRADE_VERSIONS == \"\""]
  if {[llength $definitions] < 1} {
    error "Required installed Xilinx IP is unavailable: $ip"
  }
  puts "P06_INSTALLED_IP $ip $definitions"
}
puts "P06_PREFLIGHT_PASS catalog only; licensing and synthesis remain to be tested"
