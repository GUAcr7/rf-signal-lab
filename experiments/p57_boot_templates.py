"""P57 changes only the P43 app launcher/control, retaining all hardware gates."""
from p43_boot_templates import render as base_render,sha,replace_once,WORK

MODEL_SHA='bd571ef0d30b76cdb8138d3ebd90f55463eb5439bd4c78636555bc8800873457'
DURATION=900000

def render(directory,armed_boot,monitor_sha,bit,bit_sha,dtbo,dtbo_sha):
    files=base_render(directory,armed_boot,monitor_sha,bit,bit_sha,dtbo,dtbo_sha)
    launcher=('#!/bin/sh\nd='+WORK+'\n'
        'export P56_CONTROL_FILE="$d/control" P56_SHOT_FILE="$d/shot"\n'
        'timeout -k 22 930 "$d/monitor" "$d/data" 900000 500 >"$d/log" 2>&1 &\n'
        'p=$!\necho "$p" >"$d/pid"\nwait "$p"\nr=$?\nprintf "%s\\n" "$r" >"$d/exit"\n').encode('ascii')
    control=files['control'].decode('ascii')
    control=replace_once(control,'    status) cat "$W/data/progress.json"; exit $? ;;',
        '    status) cat "$W/data/progress.json" && cat "$W/data/ai.json"; exit $? ;;\n'
        '    calibrate)\n'
        '        [ "$#" -eq 2 ] || exit 2\n'
        '        [ "${#2}" -eq 32 ] || exit 2\n'
        '        case "$2" in *[!0-9a-fA-F]*) exit 2;; esac\n'
        '        ;;')
    control=replace_once(control,'if [ -f "$W/exit" ]; then',
        'if [ -f "$W/exit" ]; then\n    [ "$1" != calibrate ] || fail "RX already stopped"')
    control=replace_once(control,'kill -TERM "$p" || fail "signal failed"',
        'if [ "$1" = calibrate ]; then\n'
        '    # Caller must first verify the known source is OFF; no RF writes here.\n'
        '    printf "P56CAL1 %s %s %s\\n" "$CURRENT" '+MODEL_SHA+' "$2" > "$W/control.next" || fail "request write"\n'
        '    mv "$W/control.next" "$W/control" || fail "request commit"\n'
        '    exit 0\nfi\n'
        'kill -TERM "$p" || fail "signal failed"')
    control=control.encode('ascii')
    runtime=files['bringup'].decode('ascii').replace(sha(files['run']),sha(launcher))
    runtime=replace_once(runtime,'MONITOR_LAUNCH duration_ms=0','MONITOR_LAUNCH duration_ms=900000')
    runtime=runtime.encode('ascii')
    wrapper=files['boot'].decode('ascii').replace(sha(files['bringup']),sha(runtime)).replace(sha(files['control']),sha(control))
    return {**files,'run':launcher,'control':control,'bringup':runtime,'boot':wrapper.encode('ascii')}
