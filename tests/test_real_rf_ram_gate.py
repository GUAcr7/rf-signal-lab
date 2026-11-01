"""Avoid accepting persistent storage or rejecting the standard Yocto symlink."""
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'experiments'))
from p52_ram import validate_ram_tmp

def test_yocto_symlink_on_volatile_tmpfs_passes():
    assert validate_ram_tmp('/dev/root / ext4 rw 0 0\ntmpfs /var/volatile tmpfs rw 0 0','/var/volatile/tmp')=='/var/volatile/tmp'

def test_literal_tmp_mount_passes():
    assert validate_ram_tmp('tmpfs /tmp tmpfs rw 0 0','/tmp')=='/tmp'

@pytest.mark.parametrize('mounts,resolved',[
    ('/dev/root / ext4 rw 0 0','/tmp'),
    ('tmpfs /var/volatile tmpfs rw 0 0\n/dev/sda /var/volatile/tmp ext4 rw 0 0','/var/volatile/tmp'),
    ('tmpfs / tmpfs rw 0 0','/unexpected'),
])
def test_unknown_or_nested_persistent_storage_rejected(mounts,resolved):
    with pytest.raises(ValueError):validate_ram_tmp(mounts,resolved)
