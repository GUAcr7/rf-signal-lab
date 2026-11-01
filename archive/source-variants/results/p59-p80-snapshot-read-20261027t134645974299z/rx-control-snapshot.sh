#!/bin/sh
# Read-only full RX control snapshot. Host must require every field plus complete.
set -eu
d=$1; w=$2; shift 2
case "$d" in /etc/p43-????????T??????Z) ;; *) exit 2;; esac
test "$w" = /run/p42-000043 || exit 2
text() { printf '%s:' "$1"; printf '%s' "$2" | base64 | tr -d '\n'; printf '\n'; }
file() { test -r "$2"; text "$1" "$(cat "$2")"; }
optional() { if test -f "$2"; then file "$1" "$2"; else text "$1" ''; fi; }
text schema rfsig.rx_control_snapshot.v1
file boot_before /proc/sys/kernel/random/boot_id
optional progress "$w/data/progress.json"
file taint /proc/sys/kernel/tainted
ir=/sys/bus/iio/devices
names=''; phy=''; adc=''; dac=''
for n in "$ir"/iio:device*; do
    name=$(cat "$n/name")
    names="$names
__D__$n:$name"'__E__'
    case "$name" in
      ad9361-phy) test -z "$phy"; phy=$n;;
      cf-ad9361-lpc) test -z "$adc"; adc=$n;;
      cf-ad9361-dds-core-lpc) test -z "$dac"; dac=$n;;
    esac
done
test -n "$phy" && test -n "$adc" && test -n "$dac"
text names "$names"
for attr in in_voltage_sampling_frequency in_voltage_rf_bandwidth \
    out_altvoltage0_RX_LO_frequency in_voltage0_gain_control_mode \
    in_voltage0_hardwaregain in_voltage0_rf_port_select; do
    file "rf_$attr" "$phy/$attr"
done
file rx_buffer "$adc/buffer/enable"
file tx_buffer "$dac/buffer/enable"
for i in 0 1 2 3; do file "scan_$i" "$adc/scan_elements/in_voltage${i}_en"; done
for name in "$@"; do
    case "$name" in original|monitor|control|run|bringup|boot|previous-boot) ;; *) exit 2;; esac
    sum=$(sha256sum "$d/$name")
    text "sha_$name" "${sum%% *}"
done
sum=$(sha256sum /etc/rcS.d/S99board)
text selected_wrapper_sha256 "${sum%% *}"
optional init_boot_marker /run/p43-init-boot
optional exit_code "$w/exit"
optional owned_pid "$w/pid"
pid=$(cat "$w/pid" 2>/dev/null || true)
case "$pid" in
  ''|*[!0-9]*) argv='';;
  *) if test -f "/proc/$pid/cmdline"; then
         argv=$(tr '\000' '\n' 2>/dev/null <"/proc/$pid/cmdline" || true)
     else argv=''; fi;;
esac
text owned_timeout_argv "$argv"
optional ai "$w/data/ai.json"
optional summary "$w/data/summary.json"
text kernel_tail "$(dmesg | tail -n 160)"
optional later_progress "$w/data/progress.json"
file boot_after /proc/sys/kernel/random/boot_id
text complete yes
