set_param general.maxThreads 2
open_project {E:/FPGA_Tools/Work/p29-vendor-20261019T082112Z/display/axi_video_display.xpr}
report_ip_status -file {E:/FPGA_Tools/Work/p29-vendor-20261019T082112Z/display-ip-status.rpt}
puts "P29_DISPLAY_IPS [get_ips -quiet]"
puts "P29_DISPLAY_PART [get_property PART [current_project]]"
puts "P29_DISPLAY_PROJECT_OPENED"
close_project
exit 0
