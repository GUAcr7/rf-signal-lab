"""Execute the real one-shot shells against a temporary filesystem in WSL.

Only the test copies remap absolute paths and mock hardware side effects. This
checks shell control flow, restore order and fail-closed behavior, not drivers.
"""
import hashlib
from pathlib import Path
import re
import subprocess
import sys
import time
import pytest

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'experiments'))
from p41_boot_templates import render_runtime,render_boot
from p36_build_rx_full import posix

STAMP='20261021T160000Z'
ARMED='00000000-0000-0000-0000-000000000001'
FRESH='00000000-0000-0000-0000-000000000002'


def digest(data):return hashlib.sha256(data).hexdigest()


def scenario(tmp_path,kind):
    base=tmp_path/'root';base.mkdir();linux=posix(base)
    def put(name,data):
        path=base/name.lstrip('/');path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(data if isinstance(data,bytes) else data.encode());return path
    guard=b'#!/bin/sh\ntest -e "'+linux.encode()+b'/sys/bus/iio/devices/iio-device1/name"\n'
    monitor=b'#!/bin/sh\nmkdir "$1"\necho ran > "$1/ran"\n'
    bit=b'test native bytes';dtbo=b'test DT bytes'
    backup='/etc/p35-guard-'+STAMP;runtime='/etc/p41-'+STAMP+'/bringup'
    app='/etc/p41-'+STAMP+'/monitor';bit_path='/lib/firmware/p35-ttl-'+STAMP+'.bin'
    dtbo_path='/lib/firmware/p35-merged-'+STAMP+'.dtbo';work='/tmp/p35-p39-160000'
    put(backup,guard);put('/etc/rcS.d/S99board','temporary wrapper')
    put(app,monitor);put(bit_path,bit);put(dtbo_path,dtbo)
    put('/etc/board-mode','rf\n');put('/proc/sys/kernel/tainted','0\n')
    put('/proc/sys/kernel/random/boot_id',(ARMED if kind=='old_boot' else FRESH)+'\n')
    put('/sys/class/gpio/gpio914/direction','in');put('/sys/class/gpio/gpio914/value','0')
    firmware=put('/sys/class/fpga_manager/fpga0/firmware','')
    put('/sys/class/fpga_manager/fpga0/state','operating\n')
    ov=base/'sys/kernel/config/device-tree/overlays';ov.mkdir(parents=True)
    put('/proc/mounts','none '+linux+'/sys/kernel/config configfs rw 0 0\n')
    (base/'run').mkdir();(base/'tmp').mkdir()
    put('/sys/kernel/debug/clk/clk_summary','clk_out1 1 1 32999000 0 0\n')
    put('/sys/class/vtconsole/vtcon0/name','(S) dummy device\n')
    put('/sys/class/vtconsole/vtcon0/bind','1\n')
    put('/sys/class/vtconsole/vtcon1/name','(M) frame buffer device\n')
    put('/sys/class/vtconsole/vtcon1/bind','1\n')
    fakebin=base/'mockbin';fakebin.mkdir()
    put('/mockbin/mount','#!/bin/sh\nexit 0\n');put('/mockbin/sync','#!/bin/sh\nexit 0\n')
    put('/mockbin/sleep','#!/bin/sh\nexit 0\n')
    # Kernel side effects are modeled only when the exact overlay bytes are read.
    create='''
for pair in '0 ad9361-phy' '1 cf-ad9361-lpc' '2 cf-ad9361-dds-core-lpc'; do
 set -- $pair; d="$T/sys/bus/iio/devices/iio:device$1"; mkdir -p "$d"; printf '%s\n' "$2" > "$d/name"
done
P="$T/sys/bus/iio/devices/iio:device0"
A="$T/sys/bus/iio/devices/iio:device1"
mkdir -p "$A/buffer" "$A/scan_elements" "$T/dev"
echo 0 > "$A/buffer/enable"
for i in 0 1 2 3; do echo 0 > "$A/scan_elements/in_voltage${i}_en"; done
echo 30720000 > "$P/in_voltage_sampling_frequency"
echo 18000000 > "$P/in_voltage_rf_bandwidth"
echo A_BALANCED > "$P/in_voltage0_rf_port_select"
touch "$T/dev/fb0"
'''
    cat='#!/bin/sh\nT='+linux+'\n'
    cat+='if [ "$1" = "'+linux+dtbo_path+'" ]; then\n'
    if kind!='probe_failure':cat+=create
    # create uses set -- so retain the exact input file for final output.
    cat+='/bin/cat "'+linux+dtbo_path+'"\nexit $?\nfi\n'
    cat+='case "$1" in */in_voltage0_hardwaregain) if [ "$(/bin/cat "$1")" = 0 ]; then echo "0.000000 dB"; exit 0; fi;; esac\n/bin/cat "$@"\n'
    put('/mockbin/cat',cat.replace('iio:device','iio-device'))
    if kind=='existing_overlay':(ov/'old').mkdir()
    if kind=='existing_RF':put('/sys/bus/iio/devices/iio-device0/name','ad9361-phy\n')
    if kind=='wrong_guard':put(backup,'changed')
    bit_sha=digest(b'wrong') if kind=='wrong_bit' else digest(bit)
    text=render_runtime(app,digest(monitor),bit_path,bit_sha,dtbo_path,digest(dtbo),digest(guard),ARMED,work,3000).decode()
    def remap(text):
        # Match only original absolute path starts, not /sys inside /proc/sys,
        # and never revisit the newly inserted test-root path.
        text=re.sub(r'(?<![A-Za-z0-9_./-])/(?:lib/firmware|sys|etc|proc|run|dev|tmp)/',lambda m:linux+m[0],text)
        # Colon directories cannot be created through the Windows filesystem.
        return text.replace('iio:device','iio-device')
    text=remap(text).replace('PATH=/sbin:/bin:/usr/sbin:/usr/bin','PATH='+posix(fakebin)+':/sbin:/bin:/usr/sbin:/usr/bin')
    text=text.replace('[ -c '+linux+'/dev/fb0 ]','[ -f '+linux+'/dev/fb0 ]')
    runtime_file=put(runtime,text)
    runtime_sha=digest(b'wrong') if kind=='wrong_runtime' else digest(runtime_file.read_bytes())
    boot=put('/boot.sh',remap(render_boot(backup,digest(guard),ARMED,runtime,runtime_sha).decode()))
    cmd='chmod +x '+posix(fakebin)+'/* '+posix(base/app.lstrip('/'))+'; PATH='+posix(fakebin)+':/usr/bin:/bin sh '+posix(boot)
    result=subprocess.run(['wsl.exe','--exec','sh','-c',cmd],capture_output=True,timeout=30)
    return base,firmware,guard,result


def test_real_shell_restores_guard_then_launches_surviving_child(tmp_path):
    base,firmware,guard,result=scenario(tmp_path,'pass')
    assert result.returncode==0,result.stdout+result.stderr
    assert (base/'etc/rcS.d/S99board').read_bytes()==guard
    log=(base/'run/p41-boot.log').read_text()
    assert log.index('ORIGINAL_GUARD_VERIFIED')<log.index('PL_ATTEMPT=1')<log.index('OVERLAY_ATTEMPT=1')<log.index('BOUNDED_MONITOR_LAUNCHED')
    assert firmware.read_text().strip()=='p35-ttl-'+STAMP+'.bin'
    end=time.monotonic()+3
    while not (base/'tmp/p35-p39-160000/exit').exists() and time.monotonic()<end:time.sleep(.02)
    assert (base/'tmp/p35-p39-160000/exit').read_text().strip()=='0'
    assert (base/'tmp/p35-p39-160000/data/ran').is_file()
    assert (base/'sys/class/vtconsole/vtcon0/bind').read_text().strip()=='1'
    assert (base/'sys/class/vtconsole/vtcon1/bind').read_text().strip()=='0'


@pytest.mark.parametrize('kind',['old_boot','wrong_guard','wrong_runtime','wrong_bit','existing_overlay','existing_RF'])
def test_failed_gate_never_programs_PL(tmp_path,kind):
    base,firmware,guard,result=scenario(tmp_path,kind)
    assert result.returncode!=0
    assert firmware.read_bytes()==b''
    assert not (base/'tmp/p35-p39-160000').exists()
    if kind not in ('old_boot','wrong_guard'):assert (base/'etc/rcS.d/S99board').read_bytes()==guard


def test_probe_failure_has_no_second_PL_or_overlay_attempt(tmp_path):
    base,firmware,guard,result=scenario(tmp_path,'probe_failure')
    assert result.returncode!=0
    log=(base/'run/p41-boot.log').read_text()
    assert log.count('PL_ATTEMPT=1')==1 and log.count('OVERLAY_ATTEMPT=1')==1
    assert 'RF incomplete; no hot retry' in log
    assert not (base/'tmp/p35-p39-160000').exists()
    assert (base/'etc/rcS.d/S99board').read_bytes()==guard
