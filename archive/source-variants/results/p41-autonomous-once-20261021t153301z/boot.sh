#!/bin/sh
# Exactly one fresh-boot hold. Restore the verified startup guard FIRST.
# This file never loads PL, applies/removes overlays, transmits, or reboots.
case "$1" in
    ""|start) ;;
    stop) exit 0 ;;
    *) exit 2 ;;
esac
GUARD=/etc/p35-guard-20261021T153301Z
GUARD_SHA=89183f1fe397f8bc20bd0c39544f5d30c37a8f1ca4e440c8cce6841d9b1247f2
ARMED_BOOT=cebdb199-ca75-4df5-9d4c-9c4f94e9f08f
INSTALL=/etc/rcS.d/S99board
RESTORE=/etc/rcS.d/.p35-restore
fail() { echo "p35-hold: FAILED: $*" >&2; exit 1; }
CURRENT=$(cat /proc/sys/kernel/random/boot_id) || fail "boot identity unreadable"
[ -n "$CURRENT" ] && [ "$CURRENT" != "$ARMED_BOOT" ] \
    || fail "fresh boot required; refusing armed-session execution"
actual=$(sha256sum "$GUARD") || fail "guard unreadable"
[ "${actual%% *}" = "$GUARD_SHA" ] || fail "guard hash mismatch"
if [ ! -d /sys/class/gpio/gpio914 ]; then
    echo 914 > /sys/class/gpio/export 2>/dev/null
fi
echo out > /sys/class/gpio/gpio914/direction || fail "fan direction"
echo 1 > /sys/class/gpio/gpio914/value || fail "fan value"
[ ! -e "$RESTORE" ] || fail "restore staging path already exists"
cp "$GUARD" "$RESTORE" || fail "restore copy"
chmod 755 "$RESTORE" || fail "restore mode"
actual=$(sha256sum "$RESTORE") || fail "restore hash read"
[ "${actual%% *}" = "$GUARD_SHA" ] || fail "restore hash mismatch"
mv "$RESTORE" "$INSTALL" || fail "restore rename"
sync || fail "restore sync"
actual=$(sha256sum "$INSTALL") || fail "installed guard unreadable"
[ "${actual%% *}" = "$GUARD_SHA" ] || fail "installed guard mismatch"
echo "$CURRENT" > /run/p35-hold-boot || fail "hold marker"
echo "p35-hold: RESTORED_GUARD_AND_HELD boot=$CURRENT"
p=/etc/p41-20261021T153301Z/bringup
actual=$(sha256sum "$p") || exit 1
[ "${actual%% *}" = bd8fdfdacce0b2a13a2411ad2f6b61650f1f933ae44ddfca6a96ab0f7901b1cb ] || exit 1
exec timeout -k 5 40 sh "$p"
