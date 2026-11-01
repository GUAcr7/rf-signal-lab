import hashlib,re,subprocess,sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'experiments'))
from p44_display_policy import render
from p36_build_rx_full import posix

def scenario(tmp_path,kind,action='start'):
    base=tmp_path/'root';base.mkdir();linux=posix(base);d='/etc/p44-20261022T040000Z'
    def put(name,data):
        f=base/name.lstrip('/');f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(data if isinstance(data,bytes) else data.encode());return f
    original=('#!/bin/sh\n# killproc xinit\n# xinit /etc/X11/Xsession\necho "$*" >> '+linux+'/calls\n').encode()
    files=render(d,original)
    def remap(text):return re.sub(r'(?<![A-Za-z0-9_./-])/(?:sys|etc|proc|run|dev)/',lambda m:linux+m[0],text)
    awake=remap(files['awake'].decode()).replace('[ -c ','[ -f ').encode()
    boot=files['boot'].decode().replace(hashlib.sha256(files['awake']).hexdigest(),hashlib.sha256(awake).hexdigest())
    put(d+'/awake',awake);put(d+'/xserver-original',original);wrapper=put('/wrapper',remap(boot))
    put('/proc/sys/kernel/random/boot_id','current\n');put('/run/p43-init-boot','old\n' if kind=='old_boot' else 'current\n')
    put('/run/p43-boot.log','p43: PERSISTENT_MONITOR_READY\n' if kind!='not_ready' else '')
    if kind!='no_progress':put('/run/p42-000043/data/progress.json','{}')
    put('/sys/module/kernel/parameters/consoleblank','600' if kind=='wake_failed' else '0')
    put('/sys/class/graphics/fb0/blank','4');put('/dev/tty1','');put('/dev/fb0','')
    if kind=='bad_original':put(d+'/xserver-original','bad')
    if kind=='bad_awake':put(d+'/awake','bad')
    result=subprocess.run(['wsl.exe','--exec','sh','-c','chmod +x '+linux+d+'/*;sh '+posix(wrapper)+' '+action],capture_output=True,timeout=15)
    return base,result

@pytest.mark.parametrize('action',['start','restart'])
def test_RF_terminal_owns_display_and_uses_normal_blank_interfaces(tmp_path,action):
    base,r=scenario(tmp_path,'pass',action)
    assert r.returncode==0,r.stdout+r.stderr
    assert (base/'calls').read_text().splitlines()==['stop']
    assert (base/'sys/class/graphics/fb0/blank').read_text().strip()=='0'
    assert b'\x1b[9;0]' in (base/'dev/tty1').read_bytes()
    assert (base/'run/p44-display-policy').read_text().strip()=='RF_PANEL_NO_X_DPMS'

@pytest.mark.parametrize('kind',['old_boot','not_ready','no_progress'])
def test_other_modes_delegate_original_X_start_unchanged(tmp_path,kind):
    base,r=scenario(tmp_path,kind)
    assert r.returncode==0
    assert (base/'calls').read_text().strip()=='start'
    assert not (base/'run/p44-display-policy').exists()

@pytest.mark.parametrize('kind',['bad_original','bad_awake','wake_failed'])
def test_hash_or_wake_failure_never_claims_standalone_display_ready(tmp_path,kind):
    base,r=scenario(tmp_path,kind)
    assert r.returncode!=0
    assert not (base/'run/p44-display-policy').exists()

def test_stop_always_delegates_service_stop(tmp_path):
    base,r=scenario(tmp_path,'pass','stop')
    assert r.returncode==0 and (base/'calls').read_text().strip()=='stop'
