#!/bin/sh
# RAM-only detached supervisor. Never changes PHY settings or boot files.
# Usage: source-job.sh bank job signal seconds boot waveform_sha nonce
set -u
umask 077
test "$#" = 7 || exit 2
bank=$1; job=$2; sig=$3; dur=$4; boot=$5; hash=$6; nonce=$7
case "$bank" in /tmp/p35-p59-????????T??????Z) ;; *) exit 2;; esac
case "$job" in "$bank"/job-????????) ;; *) exit 2;; esac
case "$sig" in tone|bpsk|qpsk|qam16) ;; *) exit 2;; esac
case "$dur" in ''|*[!0-9]*) exit 2;; esac
test "$dur" -ge 8 && test "$dur" -le 60 || exit 2
test "${#nonce}" = 8 || exit 2
case "$nonce" in *[!0-9a-f]*) exit 2;; esac
test "$job" = "$bank/job-$nonce" || exit 2
test "${#hash}" = 64 || exit 2
case "$hash" in *[!0-9a-f]*) exit 2;; esac
test "$(cat /proc/sys/kernel/random/boot_id)" = "$boot" || exit 2
test -d "$job" && test ! -L "$job" || exit 2
test ! -e "$job/receipt.json" && test ! -e "$job/native.log" || exit 2
cd "$bank" || exit 2
./guard --run "$sig" 131072 30720000 2450000000 18000000 -10 \
    "$dur" "boot-session:$boot" A "$hash" RF_LINK_REVIEWED \
    </dev/null >"$job/native.log" 2>&1 &
child=$!
start=$(awk '{print $22}' "/proc/$child/stat" 2>/dev/null)
exe=$(readlink "/proc/$child/exe" 2>/dev/null)
stop_seen=false
signal_sent=false
identity_valid=false
test "$exe" = "$bank/guard" && test -n "$start" && identity_valid=true
printf '%s\n' "$child" >"$job/child.pid"
# This noninteractive shell owns the child. It never acts on host-provided PID.
# On loss of the computer the unchanged native guard retains its own deadline;
# the native monotonic watchdog/alarm provides the previously validated bound.
# This P201 BusyBox has no external timeout applet; never assume one exists.
while kill -0 "$child" 2>/dev/null; do
    if test -e "$job/stop" && test "$stop_seen" = false; then
        stop_seen=true
        if test "$identity_valid" = true &&
           test "$(cat /proc/sys/kernel/random/boot_id)" = "$boot" &&
           test "$(readlink "/proc/$child/exe" 2>/dev/null)" = "$exe" &&
           test "$(awk '{print $22}' "/proc/$child/stat" 2>/dev/null)" = "$start"; then
            kill -TERM "$child" && signal_sent=true
        fi
    fi
    sleep 0.1
done
wait "$child"
code=$?
printf '{"schema":"rfsig.source_job.v1","nonce":"%s","boot_id":"%s","signal":"%s","seconds":%s,"child_pid":%s,"start_ticks":"%s","identity_valid":%s,"stop_seen":%s,"signal_sent":%s,"exit_code":%s,"child_reaped":true}\n' \
    "$nonce" "$boot" "$sig" "$dur" "$child" "$start" "$identity_valid" "$stop_seen" "$signal_sent" "$code" >"$job/receipt.tmp"
mv "$job/receipt.tmp" "$job/receipt.json"
exit "$code"
