#!/bin/sh
PATH=/sbin:/bin:/usr/sbin:/usr/bin
export PATH
W=/run/p42-000043
fail() { echo "p43-control: FAILED: $*" >&2; exit 1; }
case "$1" in
    status) cat "$W/data/progress.json" && cat "$W/data/ai.json"; exit $? ;;
    calibrate)
        [ "$#" -eq 2 ] || exit 2
        [ "${#2}" -eq 32 ] || exit 2
        case "$2" in *[!0-9a-fA-F]*) exit 2;; esac
        ;;
    stop) ;;
    *) exit 2 ;;
esac
CURRENT=$(cat /proc/sys/kernel/random/boot_id) || fail "boot identity"
[ "$(cat /run/p43-init-boot)" = "$CURRENT" ] || fail "wrong boot marker"
if [ -f "$W/exit" ]; then
    [ "$1" != calibrate ] || fail "RX already stopped"
    case "$(cat "$W/exit")" in 0|143) exit 0;; *) fail "previous nonzero exit";; esac
fi
p=$(cat "$W/pid") || fail "missing PID"
case "$p" in ''|*[!0-9]*|0|1) fail "invalid owned PID";; esac
cmd=$(tr '\000' '\n' < "/proc/$p/cmdline") || fail "PID command unavailable"
[ "$(printf '%s\n' "$cmd" | head -n 1)" = timeout ] || fail "not owned timeout"
printf '%s\n' "$cmd" | grep -Fx "$W/monitor" >/dev/null || fail "not owned monitor"
if [ "$1" = calibrate ]; then
    # Caller must first verify the known source is OFF; no RF writes here.
    printf "P56CAL1 %s %s %s\n" "$CURRENT" bd571ef0d30b76cdb8138d3ebd90f55463eb5439bd4c78636555bc8800873457 "$2" > "$W/control.next" || fail "request write"
    mv "$W/control.next" "$W/control" || fail "request commit"
    exit 0
fi
kill -TERM "$p" || fail "signal failed"
i=0
while [ ! -f "$W/exit" ]; do
    i=$((i+1)); [ "$i" -lt 80 ] || fail "completion unknown"
    sleep 0.1
done
case "$(cat "$W/exit")" in 0|143) exit 0;; *) fail "nonzero exit";; esac
