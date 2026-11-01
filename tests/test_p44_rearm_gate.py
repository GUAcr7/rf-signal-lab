import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'experiments'))
from p43_finish_enable import current_warm_matches

def pair():
    old=dict(expected_boot='old',installed_directory='/etc/p43-20261022T030856Z',installed_files_sha256={'boot':'exact'})
    new=dict(old,expected_boot='new',reboots_issued=1,fresh_empty_boot_verified=True)
    return old,new

def test_current_warm_boot_keeps_exact_profile():
    old,new=pair();assert current_warm_matches(old,new) is new

@pytest.mark.parametrize('key,value',[('expected_boot','old'),('reboots_issued',0),('fresh_empty_boot_verified',False),
    ('startup_origin','user_confirmed_power_cycle'),('installed_directory','other'),('installed_files_sha256',{'boot':'different'})])
def test_unconfirmed_or_different_profile_cannot_rearm(key,value):
    old,new=pair();new[key]=value
    with pytest.raises(ValueError):current_warm_matches(old,new)
