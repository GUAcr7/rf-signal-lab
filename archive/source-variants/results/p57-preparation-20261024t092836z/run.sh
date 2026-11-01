#!/bin/sh
d=/run/p42-000043
export P56_CONTROL_FILE="$d/control" P56_SHOT_FILE="$d/shot"
timeout -k 22 930 "$d/monitor" "$d/data" 900000 500 >"$d/log" 2>&1 &
p=$!
echo "$p" >"$d/pid"
wait "$p"
r=$?
printf "%s\n" "$r" >"$d/exit"
