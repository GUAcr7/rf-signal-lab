#!/bin/sh
# Collect the evidence needed to judge whether the merged RF+display design came up.
#
# This runs AFTER a reboot into the merged overlay. It only reads; it changes
# nothing. Output is deliberately compact: the serial console wraps near 80
# columns, so dumping dmesg in full would be unreadable.
#
# Usage: p32-verify.sh

echo "=== p32-verify ==="
echo "mode=$(cat /etc/board-mode 2>/dev/null)"

echo "--- fabric"
cat /sys/class/fpga_manager/fpga0/state 2>/dev/null || echo "no fpga_manager"

echo "--- iio devices"
ls /sys/bus/iio/devices/ 2>/dev/null
for name in ad9361-phy cf-ad9361-lpc cf-ad9361-dds-core-lpc; do
    if [ -e "/sys/bus/iio/devices/iio:device"*"/name" ]; then :; fi
done
for d in /sys/bus/iio/devices/iio:device*; do
    [ -e "$d/name" ] && echo "$(basename "$d") $(cat "$d/name")"
done

echo "--- drm"
ls /dev/dri/ 2>/dev/null || echo "no /dev/dri"
cat /sys/class/drm/card0/device/driver/module/refcnt 2>/dev/null

echo "--- framebuffer"
for f in virtual_size bits_per_pixel stride; do
    printf '%s=' "$f"; cat "/sys/class/graphics/fb0/$f" 2>/dev/null || echo "?"
    echo
done

echo "--- backlight"
ls /sys/class/backlight/ 2>/dev/null || echo "none"

echo "--- overlay slots"
ls /sys/kernel/config/device-tree/overlays/ 2>/dev/null

echo "--- errors in dmesg"
dmesg | grep -iE 'ad9361|axi_dmac|axi-vdma|xilinx-drm|drm|fb0|fpga|overlay|ttc|pwm|Oops|BUG|WARN' | tail -40

echo "=== end p32-verify ==="
