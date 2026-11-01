#!/bin/sh
# Normal console/framebuffer interfaces only. No PWM/register/driver changes.
set -eu
[ -c /dev/tty1 ] && [ -c /dev/fb0 ]
printf '\033[9;0]\033[14;0]' > /dev/tty1
[ "$(cat /sys/module/kernel/parameters/consoleblank)" = 0 ]
echo 0 > /sys/class/graphics/fb0/blank
echo 'p44-display: console blanking disabled; framebuffer unblanked'
