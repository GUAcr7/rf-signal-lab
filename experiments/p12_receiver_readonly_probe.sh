#!/bin/sh
# Portable stdout-only inventory for the *future* receiver. No installs, writes,
# reboots, bitstreams, iiod launches, buffers, RF setters or display launches.
set -u
LC_ALL=C
export LC_ALL
echo '=== RECEIVER READONLY INVENTORY; NOT AN RF/DISPLAY PASS ==='
uname -a
for f in /etc/issue /etc/version /etc/os-release /proc/fb; do
    if [ -r "$f" ]; then echo "--- $f"; cat "$f"; fi
done
for f in /sys/firmware/devicetree/base/model /sys/firmware/devicetree/base/compatible; do
    if [ -r "$f" ]; then echo "--- $f"; tr '\000' '\n' < "$f"; fi
done
echo '--- display nodes (absence is evidence to investigate, not a driver diagnosis)'
for f in /dev/fb* /dev/dri/* /dev/input/event*; do
    if [ -e "$f" ]; then ls -l "$f"; fi
done
for f in /sys/class/graphics/fb*/name /sys/class/graphics/fb*/virtual_size /sys/class/graphics/fb*/bits_per_pixel /sys/class/drm/card*-*/status /sys/class/drm/card*-*/modes; do
    if [ -r "$f" ]; then echo "--- $f"; cat "$f"; fi
done
echo '--- installed tool paths only; tools are not launched'
for tool in iio_info iiod python3 python qmake qtpaths Xorg weston; do
    command -v "$tool" 2>/dev/null || true
done
echo '--- library filenames; no copying/replacing libraries'
for f in /lib/libc-*.so /usr/lib/libiio.so* /usr/lib/libQt5Core.so* /usr/lib/qt5/plugins/platforms/*.so; do
    if [ -e "$f" ]; then ls -l "$f"; fi
done
echo '--- IIO devices discovered by name, not numeric device index'
for d in /sys/bus/iio/devices/iio:device*; do
    if [ ! -r "$d/name" ]; then continue; fi
    echo "--- $d"
    cat "$d/name"
    for f in "$d"/scan_elements/*_type "$d"/scan_elements/*_index "$d"/in_voltage_sampling_frequency "$d"/out_voltage_sampling_frequency "$d"/in_voltage_rf_bandwidth "$d"/out_voltage_rf_bandwidth "$d"/out_altvoltage0_RX_LO_frequency "$d"/out_altvoltage1_TX_LO_frequency "$d"/in_voltage0_gain_control_mode "$d"/in_voltage0_hardwaregain "$d"/in_voltage0_rf_port_select "$d"/buffer/enable; do
        if [ -r "$f" ]; then echo "--- $f"; cat "$f"; fi
    done
done
echo '=== INVENTORY FINISHED; no receiver/screen/transmit acceptance asserted ==='
