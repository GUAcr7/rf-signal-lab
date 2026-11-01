#!/bin/sh
# Show a stored 800x480 panel on the framebuffer.
#
# Usage: show-panel.sh [qpsk|qam16|bpsk]
#
# WHY THE UNBIND IS HERE
# ----------------------
# The framebuffer console (vtcon1) mirrors kernel and console output onto the
# panel. Observed 2026-10-20: after writing an image, `bind` was still 1 and the
# picture was repainted by console traffic within minutes. Detaching the console
# first, and confirming `bind` reads 0, keeps the image stable - verified by
# re-reading the framebuffer hash after further console output.
#
# This is not a live display: the image is a snapshot rendered on the host and
# shipped as raw bytes. Live refresh needs the merged RF+display bitstream.

set -e

name="${1:-qpsk}"
file="/root/panels/${name}.fb.gz"

if [ ! -f "$file" ]; then
    echo "no such panel: $file" >&2
    echo "available:" >&2
    ls /root/panels/*.fb.gz 2>/dev/null | sed 's#.*/##; s#\.fb\.gz$##' >&2
    exit 1
fi

if [ -e /sys/class/vtconsole/vtcon1/bind ]; then
    echo 0 > /sys/class/vtconsole/vtcon1/bind
    if [ "$(cat /sys/class/vtconsole/vtcon1/bind)" != "0" ]; then
        echo "warning: framebuffer console did not detach; the image may be repainted" >&2
    fi
fi

gunzip -c "$file" > /dev/fb0
echo "showing $name ($(wc -c < "$file") bytes gzipped)"
