"""Render pinned single-boot startup scripts. No hardware access at import."""
import hashlib
import re
from p32_session import ROOT
from p35_once_merged_trial import render_hold


def render_runtime(app,app_sha,bit,bit_sha,dtbo,dtbo_sha,guard_sha,armed_boot,work,duration=120000):
    if not re.fullmatch(r'/etc/p41-\d{8}T\d{6}Z/monitor',app):raise ValueError('app path')
    if not re.fullmatch(r'/lib/firmware/p35-ttl-\d{8}T\d{6}Z\.bin',bit):raise ValueError('bit path')
    if not re.fullmatch(r'/lib/firmware/p35-merged-\d{8}T\d{6}Z\.dtbo',dtbo):raise ValueError('overlay path')
    if bit.split('p35-ttl-')[1].split('.')[0]!=dtbo.split('p35-merged-')[1].split('.')[0]:raise ValueError('artifact pair')
    if not re.fullmatch(r'/tmp/p35-p39-\d{6}',work):raise ValueError('work path')
    if not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',armed_boot):raise ValueError('boot ID')
    if type(duration) is not int or not 1000<=duration<=120000:raise ValueError('bounded duration')
    for value in (app_sha,bit_sha,dtbo_sha,guard_sha):
        if not re.fullmatch(r'[0-9a-f]{64}',value):raise ValueError('digest')
    source=(ROOT/'board/boot/p41-monitor-once.sh.in').read_text('utf-8')
    values=dict(APP=app,APP_SHA=app_sha,BIT=bit,BIT_SHA=bit_sha,DTBO=dtbo,DTBO_SHA=dtbo_sha,
                GUARD_SHA=guard_sha,ARMED_BOOT=armed_boot,WORK=work,DURATION=str(duration))
    for key,value in values.items():source=source.replace('@@'+key+'@@',value)
    if '@@' in source:raise ValueError('unrendered template')
    return source.encode('ascii')


def render_boot(backup,guard_sha,armed_boot,runtime,runtime_sha):
    if not re.fullmatch(r'/etc/p41-\d{8}T\d{6}Z/bringup',runtime):raise ValueError('runtime path')
    if not re.fullmatch(r'[0-9a-f]{64}',runtime_sha):raise ValueError('runtime digest')
    prefix=render_hold(backup,guard_sha,armed_boot).decode('ascii')
    if not prefix.endswith('exit 0\n'):raise ValueError('hold footer changed')
    tail=('p='+runtime+'\nactual=$(sha256sum "$p") || exit 1\n'
          '[ "${actual%% *}" = '+runtime_sha+' ] || exit 1\n'
          'exec timeout -k 5 40 sh "$p"\n')
    return (prefix[:-len('exit 0\n')]+tail).encode('ascii')
