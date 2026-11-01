#!/bin/sh
d=/run/p42-000043
timeout -k 22 86400 "$d/monitor" "$d/data" 0 500 >"$d/log" 2>&1 &
p=$!
echo "$p" >"$d/pid"
wait "$p"
r=$?
printf "%s\n" "$r" >"$d/exit"
