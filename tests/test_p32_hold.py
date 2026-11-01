"""Exercise one-shot recovery logic against a filesystem fixture, never UART."""
import hashlib
import re
from pathlib import Path
from test_board_rf_readiness import posix, shell

ROOT=Path(__file__).resolve().parents[1]


def fixture(tmp_path,same_boot=False,corrupt_guard=False):
    files={'proc/sys/kernel/random/boot_id':'old\n' if same_boot else 'new\n',
        'etc/p32-guard':'#!/bin/sh\necho guard\n', 'etc/rcS.d/S99board':'wrapper sentinel',
        'sys/class/gpio/gpio914/direction':'in\n','sys/class/gpio/gpio914/value':'0\n',
        'run/keep':'keep'}
    for name,data in files.items():
        dest=tmp_path/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data.encode())
    guard=tmp_path/'etc/p32-guard';expected=hashlib.sha256(guard.read_bytes()).hexdigest()
    if corrupt_guard:guard.write_bytes(b'corrupted')
    script=(ROOT/'board/boot/p32-once-hold.sh.in').read_text('utf-8').replace('@@GUARD@@','/etc/p32-guard').replace('@@GUARD_SHA@@',expected).replace('@@ARMED_BOOT@@','old')
    # Replace roots in one pass: /proc/sys/ must not be rewritten twice.
    script=re.sub(r'/(?:etc|proc|sys|run)/',lambda m:posix(tmp_path)+m[0],script)
    target=tmp_path/'hold.sh';target.write_text(script,encoding='utf-8',newline='\n')
    return target


def test_new_boot_restores_guard_and_holds_without_hardware(tmp_path):
    script=fixture(tmp_path)
    r=shell(script,'start')
    assert r.returncode==0,r.stderr
    assert (tmp_path/'etc/rcS.d/S99board').read_bytes()==(tmp_path/'etc/p32-guard').read_bytes()
    assert (tmp_path/'sys/class/gpio/gpio914/value').read_text().strip()=='1'
    assert (tmp_path/'run/p32-hold-boot').read_text().strip()=='new'
    assert b'RESTORED_GUARD_AND_HELD' in r.stdout
    assert not (tmp_path/'sys/class/fpga_manager').exists()


def test_same_boot_refuses_and_preserves_installed_script(tmp_path):
    script=fixture(tmp_path,same_boot=True)
    r=shell(script,'start')
    assert r.returncode!=0
    assert b'fresh boot required' in r.stderr
    assert (tmp_path/'etc/rcS.d/S99board').read_text()=='wrapper sentinel'
    assert not (tmp_path/'run/p32-hold-boot').exists()


def test_corrupt_backup_never_replaces_guard(tmp_path):
    script=fixture(tmp_path,corrupt_guard=True)
    r=shell(script,'start')
    assert r.returncode!=0
    assert b'guard hash mismatch' in r.stderr
    assert (tmp_path/'etc/rcS.d/S99board').read_text()=='wrapper sentinel'
    assert not (tmp_path/'run/p32-hold-boot').exists()


def test_rename_failure_cannot_leave_extra_automatic_start_script(tmp_path):
    script=fixture(tmp_path)
    tools=tmp_path/'mock-tools';tools.mkdir()
    (tools/'mv').write_text('#!/bin/sh\nexit 13\n',encoding='utf-8',newline='\n')
    runner=tmp_path/'runner.sh'
    runner.write_text(f'chmod 755 "{posix(tools)}/mv"\nPATH="{posix(tools)}:/usr/bin:/bin"\nexport PATH\nexec /bin/sh "{posix(script)}" start\n',encoding='utf-8',newline='\n')
    r=shell(runner)
    assert r.returncode!=0
    assert b'restore rename' in r.stderr
    assert (tmp_path/'etc/rcS.d/S99board').read_text()=='wrapper sentinel'
    assert [p.name for p in (tmp_path/'etc/rcS.d').glob('S*')]==['S99board']
    assert (tmp_path/'etc/rcS.d/.p32-restore').read_bytes()==(tmp_path/'etc/p32-guard').read_bytes()
