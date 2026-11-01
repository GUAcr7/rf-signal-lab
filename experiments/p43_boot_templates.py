"""Render persistent startup using the unchanged P41 hardware initialization gates."""
import hashlib,re
from p32_session import ROOT

WORK='/run/p42-000043'
def sha(data):return hashlib.sha256(data).hexdigest()
def replace_once(text,old,new):
    if text.count(old)!=1:raise ValueError('P41 source contract changed: '+old)
    return text.replace(old,new,1)

def render(directory,armed_boot,monitor_sha,bit,bit_sha,dtbo,dtbo_sha):
    if not re.fullmatch(r'/etc/p43-\d{8}T\d{6}Z',directory):raise ValueError('install directory')
    if not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',armed_boot):raise ValueError('boot UUID')
    if not re.fullmatch(r'/lib/firmware/p35-ttl-\d{8}T\d{6}Z\.bin',bit):raise ValueError('bit path')
    if not re.fullmatch(r'/lib/firmware/p35-merged-\d{8}T\d{6}Z\.dtbo',dtbo):raise ValueError('DTBO path')
    if bit.split('p35-ttl-')[1].split('.')[0]!=dtbo.split('p35-merged-')[1].split('.')[0]:raise ValueError('artifact pair')
    for digest in (monitor_sha,bit_sha,dtbo_sha):
        if not re.fullmatch('[0-9a-f]{64}',digest):raise ValueError('SHA')
    original=(ROOT/'board/boot/S99board').read_bytes();guard_sha=sha(original)
    control=(ROOT/'board/boot/p43-monitor-control.sh.in').read_bytes()
    launcher=('#!/bin/sh\nd='+WORK+'\n'
        'timeout -k 22 86400 "$d/monitor" "$d/data" 0 500 >"$d/log" 2>&1 &\n'
        'p=$!\necho "$p" >"$d/pid"\nwait "$p"\nr=$?\nprintf "%s\\n" "$r" >"$d/exit"\n').encode('ascii')
    source=(ROOT/'board/boot/p41-monitor-once.sh.in').read_text('utf-8')
    source=replace_once(source,'# Called ONLY after the one-shot hold restored the original guard on a fresh boot.',
        '# P43: called by a pinned persistent guard on a new, empty boot.')
    source=source.replace('p41','p43')
    source=replace_once(source,'/run/p35-hold-boot','/run/p43-init-boot')
    source=replace_once(source,'hash_is /etc/rcS.d/S99board "$GUARD_SHA"',f'hash_is {directory}/original "$GUARD_SHA"')
    source=source.replace('ORIGINAL_GUARD_VERIFIED','ORIGINAL_BACKUP_VERIFIED')
    source=replace_once(source,'hash_is "$APP" "$APP_SHA" || fail "monitor hash"',
        'hash_is "$APP" "$APP_SHA" || fail "monitor hash"\nhash_is '+directory+'/run '+sha(launcher)+' || fail "launcher hash"')
    source=replace_once(source,'mount -t configfs none',"grep -q ' /run tmpfs ' /proc/mounts || fail 'run is not tmpfs'\nmount -t configfs none")
    start='mkdir "$WORK" || fail "work directory must be new"'
    source=source[:source.index(start)]+'''mkdir "$WORK" || fail "work directory must be new"
cp "$APP" "$WORK/monitor" || fail "RAM monitor copy"
chmod 755 "$WORK/monitor" || fail "RAM monitor mode"
hash_is "$WORK/monitor" "$APP_SHA" || fail "RAM monitor hash"
cp @@DIRECTORY@@/run "$WORK/run" || fail "launcher copy"
hash_is "$WORK/run" @@LAUNCHER_SHA@@ || fail "launcher hash"
mark "MONITOR_LAUNCH duration_ms=0 work=$WORK"
mark "UPTIME_AT_LAUNCH=$(cat /proc/uptime)"
sh "$WORK/run" </dev/null >/dev/null 2>&1 &
i=0
while :; do
    if grep -F '"state":"running"' "$WORK/data/progress.json" >/dev/null 2>&1; then
        break
    fi
    [ ! -e "$WORK/exit" ] || fail "monitor stopped before first progress"
    i=$((i+1)); [ "$i" -lt 20 ] || fail "first progress missing"
    sleep 0.5
done
rmdir @@DIRECTORY@@/pending || fail "initialization latch clear"
sync || fail "ready latch sync"
mark "PERSISTENT_MONITOR_READY"
exit 0
'''
    values=dict(APP=directory+'/monitor',APP_SHA=monitor_sha,BIT=bit,BIT_SHA=bit_sha,DTBO=dtbo,
        DTBO_SHA=dtbo_sha,GUARD_SHA=guard_sha,ARMED_BOOT=armed_boot,WORK=WORK,DURATION='0',
        DIRECTORY=directory,LAUNCHER_SHA=sha(launcher))
    for k,v in values.items():source=source.replace('@@'+k+'@@',v)
    if '@@' in source:raise ValueError('unrendered runtime')
    runtime=source.encode('ascii')
    wrapper=(ROOT/'board/boot/p43-persistent-guard.sh.in').read_text('utf-8')
    for k,v in dict(DIRECTORY=directory,GUARD_SHA=guard_sha,ARMED_BOOT=armed_boot,
        RUNTIME_SHA=sha(runtime),CONTROL_SHA=sha(control)).items():wrapper=wrapper.replace('@@'+k+'@@',v)
    if '@@' in wrapper:raise ValueError('unrendered wrapper')
    return dict(original=original,monitor=None,control=control,run=launcher,bringup=runtime,boot=wrapper.encode('ascii'))
