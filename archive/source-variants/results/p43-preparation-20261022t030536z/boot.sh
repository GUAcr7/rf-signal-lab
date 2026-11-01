#!/bin/sh
# Persistent selection only. Never reprogram a partially initialized boot.
PATH=/sbin:/bin:/usr/sbin:/usr/bin
export PATH
D=/etc/p43-20261022T030000Z
ORIGINAL_SHA=89183f1fe397f8bc20bd0c39544f5d30c37a8f1ca4e440c8cce6841d9b1247f2
RUNTIME_SHA=c3b285ad2f957585ab350f197cf3e845edfa3fd9068ec63244a91fa69765bb87
CONTROL_SHA=0314f55ec0f463f9e4d8283b7ab7a0839d3cee7b34ce221b57a7f2ea2a323fd5
ARMED_BOOT=00000000-0000-0000-0000-000000000001
fail() { echo "p43-guard: FAILED: $*" >&2; exit 1; }
hash_is() {
    actual=$(sha256sum "$1") || return 1
    [ "${actual%% *}" = "$2" ]
}
hash_is "$D/original" "$ORIGINAL_SHA" || fail "original guard hash"
case "$1" in
    --check-rf) shift; exec "$D/original" --check-rf "$@" ;;
    stop)
        hash_is "$D/control" "$CONTROL_SHA" || fail "control hash"
        exec sh "$D/control" stop ;;
    ""|start) ;;
    *) exit 2 ;;
esac
CURRENT=$(cat /proc/sys/kernel/random/boot_id) || fail "boot identity"
[ -n "$CURRENT" ] && [ "$CURRENT" != "$ARMED_BOOT" ] || fail "new boot required"
grep -q ' /run tmpfs ' /proc/mounts || fail "run must be tmpfs"
[ ! -e /run/p43-init-boot ] || fail "already attempted this boot"
echo "$CURRENT" > /run/p43-init-boot || fail "identity marker"
# A stale pending directory means initialization never reached first UI progress.
# This is a NEW boot: select factory RF before loading any merged hardware.
if [ -e "$D/disabled" ] || [ -d "$D/pending" ]; then
    : > "$D/disabled" || fail "fallback latch"
    sync || fail "fallback sync"
    echo "p43-guard: FACTORY_FALLBACK boot=$CURRENT"
    exec "$D/original" start
fi
hash_is "$D/bringup" "$RUNTIME_SHA" || fail "runtime hash"
hash_is "$D/control" "$CONTROL_SHA" || fail "control hash"
if [ ! -d /sys/class/gpio/gpio914 ]; then
    echo 914 > /sys/class/gpio/export 2>/dev/null
fi
echo out > /sys/class/gpio/gpio914/direction || fail "fan direction"
echo 1 > /sys/class/gpio/gpio914/value || fail "fan on"
mkdir "$D/pending" || fail "initialization latch"
sync || fail "initialization latch sync"
exec timeout -k 5 40 sh "$D/bringup"
