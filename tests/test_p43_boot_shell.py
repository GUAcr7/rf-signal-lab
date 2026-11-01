"""Execute persistent startup/control in an isolated filesystem; not driver proof."""
import hashlib,re,subprocess,sys,time
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'experiments'))
import p43_boot_templates as templates
from p36_build_rx_full import posix
STAMP='20261022T030000Z';ARMED='00000000-0000-0000-0000-000000000001';FRESH='00000000-0000-0000-0000-000000000002'
def sha(b):return hashlib.sha256(b).hexdigest()

def scenario(tmp_path,monkeypatch,kind):
    base=tmp_path/'root';base.mkdir();linux=posix(base)
    def put(path,data):
        target=base/path.lstrip('/');target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(data if isinstance(data,bytes) else data.encode());return target
    source=tmp_path/'templates';(source/'board/boot').mkdir(parents=True)
    original=('#!/bin/sh\nif [ "$1" = --check-rf ];then test -e '+linux+'/sys/bus/iio/devices/iio-device1/name;exit $?;fi\necho factory > '+linux+'/factory\n').encode()
    for f in ('p41-monitor-once.sh.in','p43-persistent-guard.sh.in','p43-monitor-control.sh.in'):
        (source/'board/boot'/f).write_bytes((ROOT/'board/boot'/f).read_bytes())
    (source/'board/boot/S99board').write_bytes(original);monkeypatch.setattr(templates,'ROOT',source)
    app=b'#!/bin/sh\nmkdir "$1"\necho \'{"state":"running"}\' > "$1/progress.json"\nsleep 15\n'
    if kind=='no_progress':app=b'#!/bin/sh\nexit 1\n'
    d='/etc/p43-'+STAMP;bit='/lib/firmware/p35-ttl-'+STAMP+'.bin';dtbo='/lib/firmware/p35-merged-'+STAMP+'.dtbo'
    files=templates.render(d,ARMED,sha(app),bit,sha(b'bit'),dtbo,sha(b'dtbo'))
    files['monitor']=app
    def remap(text):
        def subst(m):
            if m[0]=='/proc/' and text[m.end():].startswith('$p/'):return m[0]
            return linux+m[0]
        text=re.sub(r'(?<![A-Za-z0-9_./-])/(?:lib/firmware|sys|etc|proc|run|dev|tmp)/',subst,text)
        return text.replace('iio:device','iio-device').replace("' /run tmpfs '","' "+linux+"/run tmpfs '")
    launcher=remap(files['run'].decode()).encode();control=remap(files['control'].decode()).encode()
    runtime=files['bringup'].decode().replace(sha(files['run']),sha(launcher))
    runtime=remap(runtime).replace('PATH=/sbin:/bin:/usr/sbin:/usr/bin','PATH='+linux+'/mockbin:/sbin:/bin:/usr/sbin:/usr/bin')
    runtime=runtime.replace('[ -c '+linux+'/dev/fb0 ]','[ -f '+linux+'/dev/fb0 ]')
    wrapper=files['boot'].decode().replace(sha(files['bringup']),sha(runtime.encode())).replace(sha(files['control']),sha(control))
    wrapper=remap(wrapper)
    for n,b in dict(original=original,monitor=app,run=launcher,control=control,bringup=runtime.encode()).items():put(d+'/'+n,b)
    installed=put('/etc/rcS.d/S99board',wrapper)
    put(bit,b'bit');put(dtbo,b'dtbo');put('/etc/board-mode','rf\n')
    put('/proc/sys/kernel/random/boot_id',(ARMED if kind=='old_boot' else FRESH)+'\n')
    put('/proc/sys/kernel/tainted','0\n')
    mounts='none '+linux+'/sys/kernel/config configfs rw 0 0\nnone '+linux+'/run '+('ext4' if kind=='not_RAM' else 'tmpfs')+' rw 0 0\n'
    put('/proc/mounts',mounts)
    put('/sys/class/gpio/gpio914/direction','in');put('/sys/class/gpio/gpio914/value','0')
    firmware=put('/sys/class/fpga_manager/fpga0/firmware','');put('/sys/class/fpga_manager/fpga0/state','operating\n')
    ov=base/'sys/kernel/config/device-tree/overlays';ov.mkdir(parents=True)
    (base/'run').mkdir();(base/'tmp').mkdir()
    put('/sys/kernel/debug/clk/clk_summary','clk_out1 1 1 33000000 0 0\n')
    for i,name in ((0,'(S) dummy device'),(1,'(M) frame buffer device')):
        put('/sys/class/vtconsole/vtcon'+str(i)+'/name',name+'\n');put('/sys/class/vtconsole/vtcon'+str(i)+'/bind','1\n')
    fakebin=base/'mockbin';fakebin.mkdir()
    put('/mockbin/mount','#!/bin/sh\nexit 0\n')
    create='''
for pair in '0 ad9361-phy' '1 cf-ad9361-lpc' '2 cf-ad9361-dds-core-lpc';do
 set -- $pair;d="$T/sys/bus/iio/devices/iio-device$1";mkdir -p "$d";echo "$2" > "$d/name"
done
P="$T/sys/bus/iio/devices/iio-device0"
A="$T/sys/bus/iio/devices/iio-device1"
mkdir -p "$A/buffer" "$A/scan_elements" "$T/dev"
echo 0 > "$A/buffer/enable"
for i in 0 1 2 3;do echo 0 > "$A/scan_elements/in_voltage${i}_en";done
echo 30720000 > "$P/in_voltage_sampling_frequency"
echo 18000000 > "$P/in_voltage_rf_bandwidth"
echo A_BALANCED > "$P/in_voltage0_rf_port_select"
touch "$T/dev/fb0"
'''
    cat='#!/bin/sh\nT='+linux+'\nif [ "$1" = "'+linux+dtbo+'" ];then\n'
    if kind!='probe_failure':cat+=create
    cat+='/bin/cat "'+linux+dtbo+'"\nexit $?\nfi\n'
    cat+='case "$1" in */in_voltage0_hardwaregain) if [ "$(/bin/cat "$1")" = 0 ];then echo "0.000000 dB";exit 0;fi;;esac\n/bin/cat "$@"\n'
    put('/mockbin/cat',cat)
    if kind=='existing_overlay':(ov/'old').mkdir()
    if kind=='existing_RF':put('/sys/bus/iio/devices/iio-device0/name','ad9361-phy\n')
    if kind=='wrong_original':put(d+'/original','bad')
    if kind=='wrong_runtime':put(d+'/bringup','bad')
    if kind=='wrong_bit':put(bit,'bad')
    if kind=='repeat_boot':put('/run/p43-init-boot',FRESH)
    if kind=='disabled':put(d+'/disabled','')
    if kind=='pending':(base/(d+'/pending').lstrip('/')).mkdir()
    cmd='chmod +x '+linux+d+'/* '+posix(fakebin)+'/*; sh '+posix(installed)
    result=subprocess.run(['wsl.exe','--exec','sh','-c',cmd],capture_output=True,timeout=40)
    return base,d,firmware,wrapper.encode(),result

def test_persistent_shell_keeps_guard_clears_latch_and_owned_stop(tmp_path,monkeypatch):
    base,d,firmware,wrapper,r=scenario(tmp_path,monkeypatch,'pass')
    assert r.returncode==0,r.stdout+r.stderr
    assert (base/'etc/rcS.d/S99board').read_bytes()==wrapper
    assert not (base/(d+'/pending').lstrip('/')).exists()
    log=(base/'run/p43-boot.log').read_text()
    assert log.count('PL_ATTEMPT=1')==log.count('OVERLAY_ATTEMPT=1')==1
    assert 'PERSISTENT_MONITOR_READY' in log
    control=base/(d+'/control').lstrip('/')
    pid=base/'run/p42-000043/pid';owned=pid.read_bytes();pid.write_bytes(b'1\n')
    rejected=subprocess.run(['wsl.exe','--exec','sh',posix(control),'stop'],capture_output=True,timeout=15)
    assert rejected.returncode!=0 and not (base/'run/p42-000043/exit').exists()
    pid.write_bytes(owned)
    result=subprocess.run(['wsl.exe','--exec','sh',posix(control),'stop'],capture_output=True,timeout=15)
    assert result.returncode==0,result.stdout+result.stderr
    assert (base/'run/p42-000043/exit').read_text().strip()=='143'

@pytest.mark.parametrize('kind',['old_boot','wrong_original','wrong_runtime','wrong_bit','existing_overlay','existing_RF','repeat_boot','not_RAM'])
def test_failed_preconditions_never_program_PL(tmp_path,monkeypatch,kind):
    base,d,firmware,wrapper,r=scenario(tmp_path,monkeypatch,kind)
    assert r.returncode!=0
    assert firmware.read_bytes()==b''
    assert not (base/'run/p42-000043').exists()

@pytest.mark.parametrize('kind',['disabled','pending'])
def test_new_boot_disabled_or_stale_initialization_selects_factory_once(tmp_path,monkeypatch,kind):
    base,d,firmware,wrapper,r=scenario(tmp_path,monkeypatch,kind)
    assert r.returncode==0,r.stdout+r.stderr
    assert firmware.read_bytes()==b'' and (base/'factory').is_file()
    assert (base/(d+'/disabled').lstrip('/')).is_file()
    assert b'FACTORY_FALLBACK' in r.stdout

@pytest.mark.parametrize('kind',['probe_failure','no_progress'])
def test_incomplete_boot_preserves_pending_without_hot_retry(tmp_path,monkeypatch,kind):
    base,d,firmware,wrapper,r=scenario(tmp_path,monkeypatch,kind)
    assert r.returncode!=0
    log=(base/'run/p43-boot.log').read_text()
    assert log.count('PL_ATTEMPT=1')==log.count('OVERLAY_ATTEMPT=1')==1
    assert 'PERSISTENT_MONITOR_READY' not in log
    assert (base/(d+'/pending').lstrip('/')).is_dir()
