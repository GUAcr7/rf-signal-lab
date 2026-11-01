#!/bin/sh
# Exactly one fresh-boot hold. Restore the verified startup guard FIRST.
# This file never loads PL, applies/removes overlays, transmits, or reboots.
case "$1" in
    ""|start) ;;
    stop) exit 0 ;;
    *) exit 2 ;;
esac
GUARD=/etc/p35-guard-20261021T160000Z
GUARD_SHA=3333333333333333333333333333333333333333333333333333333333333333
ARMED_BOOT=00000000-0000-0000-0000-000000000001
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
p=/etc/p41-20261021T160000Z/bringup
actual=$(sha256sum "$p") || exit 1
[ "${actual%% *}" = c6732fc603b85f986188572b66e50a5335eeb9ca8e8270b62462f8708dc9efed ] || exit 1
exec timeout -k 5 40 sh "$p"
