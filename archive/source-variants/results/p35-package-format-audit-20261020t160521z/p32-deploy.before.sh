#!/bin/sh
# Install the merged RF+display bitstream as the display-mode payload.
#
# WHY THIS SHAPE
# --------------
# S99board applies exactly one overlay per boot, chosen by /etc/board-mode:
#   rf      -> ad9361.bin  + pl.dtbo      (bitstream loaded explicitly by the script)
#   display -> display.bin + d480p.dtbo   (bitstream loaded by the overlay's firmware-name)
#
# The merged overlay carries firmware-name = "rf-display-p32.bin", so it fits the
# display-mode path without touching S99board. Swapping d480p.dtbo for it is the
# smallest reversible change that boots a design containing both the radio and the
# display. Nothing here removes a bound overlay at runtime: the project already
# learned that hot-unloading this vendor overlay can Oops the kernel.
#
# Rollback: restore d480p.dtbo from the .vendor-backup copy and reboot.
#
# Usage: p32-deploy.sh [--rollback]

set -e

FW=/lib/firmware
BIN_SRC=/tmp/rf-display-p32.bin
DTBO_SRC=/tmp/rf-display-p32.dtbo
BIN_DST=$FW/rf-display-p32.bin
OVERLAY=$FW/d480p.dtbo
BACKUP=$FW/d480p.dtbo.vendor-backup

BIN_SHA=96c5d8f3a5fb8cd070e94568871c77eec6c69203212c9ed25587c3c1a885b13c
DTBO_SHA=826756c5fb3326224a2560e4d20541bc2478718b82c71da4cfad9914532b1acf

sum() { sha256sum "$1" | cut -d' ' -f1; }

if [ "$1" = "--rollback" ]; then
    [ -f "$BACKUP" ] || { echo "no vendor backup at $BACKUP" >&2; exit 1; }
    cp "$BACKUP" "$OVERLAY"
    sync
    echo "restored vendor d480p.dtbo; reboot to return to the factory display mode"
    exit 0
fi

# --- preconditions -------------------------------------------------------
[ -f "$BIN_SRC" ]  || { echo "missing $BIN_SRC" >&2; exit 1; }
[ -f "$DTBO_SRC" ] || { echo "missing $DTBO_SRC" >&2; exit 1; }
[ "$(sum "$BIN_SRC")" = "$BIN_SHA" ]   || { echo "bitstream hash mismatch" >&2; exit 1; }
[ "$(sum "$DTBO_SRC")" = "$DTBO_SHA" ] || { echo "overlay hash mismatch" >&2; exit 1; }

# An overlay is normally bound right now, because the board booted in some mode.
# That is fine: this script only copies files, and the swap takes effect at the
# next boot when S99board applies exactly one overlay. Warn rather than refuse,
# so the check cannot block a perfectly safe install.
if [ -d /sys/kernel/config/device-tree/overlays/pl ]; then
    echo "note: an overlay is currently bound; the swap applies at the next boot"
fi

# --- back up the vendor overlay once, and only once ----------------------
if [ ! -f "$BACKUP" ]; then
    cp "$OVERLAY" "$BACKUP"
    echo "backed up vendor overlay -> $BACKUP ($(sum "$BACKUP"))"
else
    echo "vendor backup already present ($(sum "$BACKUP"))"
fi

# --- install -------------------------------------------------------------
cp "$BIN_SRC" "$BIN_DST"
cp "$DTBO_SRC" "$OVERLAY"
sync

[ "$(sum "$BIN_DST")" = "$BIN_SHA" ]   || { echo "installed bitstream hash mismatch" >&2; exit 1; }
[ "$(sum "$OVERLAY")" = "$DTBO_SHA" ]  || { echo "installed overlay hash mismatch" >&2; exit 1; }

echo "installed:"
echo "  $BIN_DST  $(sum "$BIN_DST")"
echo "  $OVERLAY  $(sum "$OVERLAY")"
echo "vendor overlay preserved at $BACKUP"
echo "mode=$(cat /etc/board-mode)"
echo "reboot to boot the merged design"
