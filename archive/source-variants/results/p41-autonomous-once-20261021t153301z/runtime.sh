#!/bin/sh
# Called ONLY after the one-shot hold restored the original guard on a fresh boot.
# No retries, unbinds, overlay removal, default firmware replacement or TX.
PATH=/sbin:/bin:/usr/sbin:/usr/bin
export PATH
APP=/etc/p41-20261021T153301Z/monitor
APP_SHA=777b93620f211f4e516c5a17a1bc703c6da06663a9afeff9c9a1c3fe72f4c925
BIT=/lib/firmware/p35-ttl-20261021T090121Z.bin
BIT_SHA=1b0fac1aec86e4efeb003f9ea8d1a98d0e339e649633e31034d59e0990064405
DTBO=/lib/firmware/p35-merged-20261021T090121Z.dtbo
DTBO_SHA=fe76a72f30541e0bad273d9bb2f715718a98d4cf0e8ca375efbf4a688603a828
GUARD_SHA=89183f1fe397f8bc20bd0c39544f5d30c37a8f1ca4e440c8cce6841d9b1247f2
ARMED_BOOT=cebdb199-ca75-4df5-9d4c-9c4f94e9f08f
WORK=/tmp/p35-p39-153301
DURATION=120000
LOG=/run/p41-boot.log
mark() { echo "p41: $*"; echo "p41: $*" >> "$LOG"; }
fail() { mark "FAILED: $*"; exit 1; }
hash_is() {
    actual=$(sha256sum "$1") || return 1
    [ "${actual%% *}" = "$2" ]
}
CURRENT=$(cat /proc/sys/kernel/random/boot_id) || fail "boot identity"
[ -n "$CURRENT" ] && [ "$CURRENT" != "$ARMED_BOOT" ] || fail "fresh boot required"
[ "$(cat /run/p35-hold-boot)" = "$CURRENT" ] || fail "restored hold marker"
hash_is /etc/rcS.d/S99board "$GUARD_SHA" || fail "original guard not restored"
mark "ORIGINAL_GUARD_VERIFIED boot=$CURRENT"
[ "$(cat /etc/board-mode)" = rf ] || fail "mode must remain rf"
[ "$(cat /proc/sys/kernel/tainted)" = 0 ] || fail "kernel tainted"
hash_is "$APP" "$APP_SHA" || fail "monitor hash"
hash_is "$BIT" "$BIT_SHA" || fail "bitstream hash"
hash_is "$DTBO" "$DTBO_SHA" || fail "overlay hash"
[ -x "$APP" ] || fail "monitor not executable"
[ ! -e /dev/fb0 ] && [ ! -e /dev/dri/card0 ] || fail "display already bound"
mount -t configfs none /sys/kernel/config 2>/dev/null || true
grep -q ' /sys/kernel/config configfs ' /proc/mounts || fail "configfs unavailable"
OV=/sys/kernel/config/device-tree/overlays
[ -d "$OV" ] && [ -z "$(ls -A "$OV")" ] || fail "overlay already present"
for n in /sys/bus/iio/devices/iio:device*/name; do
    [ -r "$n" ] || continue
    case "$(cat "$n")" in
        ad9361-phy|cf-ad9361-lpc|cf-ad9361-dds-core-lpc) fail "RF already bound" ;;
    esac
done
F=/sys/class/fpga_manager/fpga0
mark "EMPTY_BINDINGS_VERIFIED"
mark "PL_ATTEMPT=1"
basename "$BIT" > "$F/firmware" || fail "PL load"
[ "$(cat "$F/state")" = operating ] || fail "PL not operating"
mkdir "$OV/p41" || fail "overlay slot"
mark "OVERLAY_ATTEMPT=1"
cat "$DTBO" > "$OV/p41/dtbo" || fail "overlay apply"
i=0
while ! /etc/rcS.d/S99board --check-rf >/dev/null 2>&1; do
    i=$((i+1)); [ "$i" -lt 12 ] || fail "RF incomplete; no hot retry"
    sleep 0.5
done
P=
A=
for required in ad9361-phy cf-ad9361-lpc cf-ad9361-dds-core-lpc; do
    count=0
    for n in /sys/bus/iio/devices/iio:device*/name; do
        [ -r "$n" ] || continue
        [ "$(cat "$n")" = "$required" ] || continue
        count=$((count+1))
        case "$required" in
            ad9361-phy) P=${n%/name} ;;
            cf-ad9361-lpc) A=${n%/name} ;;
        esac
    done
    [ "$count" -eq 1 ] || fail "RF name missing/duplicated"
done
[ "$(cat "$A/buffer/enable")" = 0 ] || fail "RX buffer active"
for n in 0 1 2 3; do
    [ "$(cat "$A/scan_elements/in_voltage${n}_en")" = 0 ] || fail "RX scan active"
done
[ "$(cat "$P/in_voltage_sampling_frequency")" = 30720000 ] || fail "sample rate"
[ "$(cat "$P/in_voltage_rf_bandwidth")" = 18000000 ] || fail "RF bandwidth"
[ "$(cat "$P/in_voltage0_rf_port_select")" = A_BALANCED ] || fail "RF port"
[ "$(cat /proc/sys/kernel/tainted)" = 0 ] || fail "kernel tainted after apply"
[ -c /dev/fb0 ] || fail "framebuffer missing"
# Software-rate gate only; host acceptance separately checks live DT and LOCK.
awk '$1=="clk_out1" && $4>=32999000 && $4<=33001000 {n++} END {exit n!=1}' \
    /sys/kernel/debug/clk/clk_summary || fail "software pixel clock"
echo manual > "$P/in_voltage0_gain_control_mode" || fail "manual gain mode"
echo 0 > "$P/in_voltage0_hardwaregain" || fail "gain write"
echo 2450000000 > "$P/out_altvoltage0_RX_LO_frequency" || fail "RX LO write"
[ "$(cat "$P/in_voltage0_gain_control_mode")" = manual ] || fail "gain mode readback"
[ "$(cat "$P/in_voltage0_hardwaregain")" = '0.000000 dB' ] || fail "gain readback"
[ "$(cat "$P/out_altvoltage0_RX_LO_frequency")" = 2450000000 ] || fail "RX LO readback"
count=0
for c in /sys/class/vtconsole/vtcon*; do
    [ -r "$c/name" ] || continue
    case "$(cat "$c/name")" in
        *'frame buffer device'*)
            count=$((count+1))
            case "$(cat "$c/bind")" in
                1) echo 0 > "$c/bind" || fail "framebuffer console detach" ;;
                0) ;;
                *) fail "invalid console binding" ;;
            esac
            ;;
    esac
done
[ "$count" -eq 1 ] || fail "framebuffer console ambiguous"
hash_is "$APP" "$APP_SHA" || fail "monitor changed before execution"
mkdir "$WORK" || fail "work directory must be new"
mark "MONITOR_LAUNCH duration_ms=$DURATION work=$WORK"
mark "UPTIME_AT_LAUNCH=$(cat /proc/uptime)"
(
    timeout -k 22 135 "$APP" "$WORK/data" "$DURATION" 500 > "$WORK/log" 2>&1
    code=$?
    printf '%s\n' "$code" > "$WORK/exit"
) </dev/null >/dev/null 2>&1 &
echo "$!" > "$WORK/launcher.pid" || fail "launcher PID record"
mark "BOUNDED_MONITOR_LAUNCHED"
exit 0
