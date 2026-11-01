#!/bin/sh
# P43: called by a pinned persistent guard on a new, empty boot.
# No retries, unbinds, overlay removal, default firmware replacement or TX.
PATH=/sbin:/bin:/usr/sbin:/usr/bin
export PATH
APP=/etc/p43-20261024T100000Z/monitor
APP_SHA=fa9a175edc2242aab64a4ce7250334ecd1a6581045f9599bcd9bea5872d025f8
BIT=/lib/firmware/p35-ttl-20261021T090121Z.bin
BIT_SHA=1111111111111111111111111111111111111111111111111111111111111111
DTBO=/lib/firmware/p35-merged-20261021T090121Z.dtbo
DTBO_SHA=2222222222222222222222222222222222222222222222222222222222222222
GUARD_SHA=89183f1fe397f8bc20bd0c39544f5d30c37a8f1ca4e440c8cce6841d9b1247f2
ARMED_BOOT=00000000-0000-0000-0000-000000000001
WORK=/run/p42-000043
DURATION=0
LOG=/run/p43-boot.log
mark() { echo "p43: $*"; echo "p43: $*" >> "$LOG"; }
fail() { mark "FAILED: $*"; exit 1; }
hash_is() {
    actual=$(sha256sum "$1") || return 1
    [ "${actual%% *}" = "$2" ]
}
CURRENT=$(cat /proc/sys/kernel/random/boot_id) || fail "boot identity"
[ -n "$CURRENT" ] && [ "$CURRENT" != "$ARMED_BOOT" ] || fail "fresh boot required"
[ "$(cat /run/p43-init-boot)" = "$CURRENT" ] || fail "restored hold marker"
hash_is /etc/p43-20261024T100000Z/original "$GUARD_SHA" || fail "original guard not restored"
mark "ORIGINAL_BACKUP_VERIFIED boot=$CURRENT"
[ "$(cat /etc/board-mode)" = rf ] || fail "mode must remain rf"
[ "$(cat /proc/sys/kernel/tainted)" = 0 ] || fail "kernel tainted"
hash_is "$APP" "$APP_SHA" || fail "monitor hash"
hash_is /etc/p43-20261024T100000Z/run 10c08f2372171ed3d60283c2b5df239517923bad6c269790c6a81e1d63e662e5 || fail "launcher hash"
hash_is "$BIT" "$BIT_SHA" || fail "bitstream hash"
hash_is "$DTBO" "$DTBO_SHA" || fail "overlay hash"
[ -x "$APP" ] || fail "monitor not executable"
[ ! -e /dev/fb0 ] && [ ! -e /dev/dri/card0 ] || fail "display already bound"
grep -q ' /run tmpfs ' /proc/mounts || fail 'run is not tmpfs'
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
mkdir "$OV/p43" || fail "overlay slot"
mark "OVERLAY_ATTEMPT=1"
cat "$DTBO" > "$OV/p43/dtbo" || fail "overlay apply"
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
cp "$APP" "$WORK/monitor" || fail "RAM monitor copy"
chmod 755 "$WORK/monitor" || fail "RAM monitor mode"
hash_is "$WORK/monitor" "$APP_SHA" || fail "RAM monitor hash"
cp /etc/p43-20261024T100000Z/run "$WORK/run" || fail "launcher copy"
hash_is "$WORK/run" 10c08f2372171ed3d60283c2b5df239517923bad6c269790c6a81e1d63e662e5 || fail "launcher hash"
mark "MONITOR_LAUNCH duration_ms=900000 work=$WORK"
mark "UPTIME_AT_LAUNCH=$(cat /proc/uptime)"
sh "$WORK/run" </dev/null >/dev/null 2>&1 &
i=0
while :; do
    if grep -F '"state":"running"' "$WORK/data/progress.json" >/dev/null 2>&1; then
        break
    fi
    [ ! -e "$WORK/exit" ] || fail "monitor stopped before first progress"
    i=$((i+1)); [ "$i" -lt 20 ] || fail "first progress missing"
    sleep 0.5
done
rmdir /etc/p43-20261024T100000Z/pending || fail "initialization latch clear"
sync || fail "ready latch sync"
mark "PERSISTENT_MONITOR_READY"
exit 0
