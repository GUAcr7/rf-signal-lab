open_project {E:/p32-pwm2-105934/project/combined.xpr}
open_bd_design [get_files */system.bd]
set old [get_bd_nets -of_objects [get_bd_ports lcd_pwm_backlight]]
set old_pins [get_bd_pins -of_objects $old]
if {[llength $old_pins] != 1 || [get_property NAME $old_pins] ne "TTC0_WAVE0_OUT"} {error "unexpected old PWM net"}
set freepin [get_bd_pins sys_ps7/TTC0_WAVE2_OUT]
if {[llength $freepin] != 1 || [llength [get_bd_nets -quiet -of_objects $freepin]] != 0} {error "TTC0 channel2 unavailable"}
disconnect_bd_net $old [get_bd_pins sys_ps7/TTC0_WAVE0_OUT]
disconnect_bd_net $old [get_bd_ports lcd_pwm_backlight]
delete_bd_objs $old
connect_bd_net -net display_backlight_ttc0_ch2 $freepin [get_bd_ports lcd_pwm_backlight]
validate_bd_design
save_bd_design
write_bd_tcl -force {E:/p32-pwm2-105934/p32-pwm2-validated.tcl}
puts "P32_PWM2_BD_VALIDATED no_synthesis_no_bitstream"
close_project
exit
