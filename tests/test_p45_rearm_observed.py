import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'experiments'))
from p43_finish_enable import current_observed_matches

def pair():
    a=dict(expected_boot='old',installed_directory='same',installed_files_sha256={'boot':'exact'})
    b=dict(a,expected_boot='new',startup_origin='existing_new_boot_power_cycle_not_verified',reboots_issued=0,
        power_cycles_observed=0,fresh_empty_boot_verified=True,inputs={})
    return a,b

def test_observed_rearm_does_not_classify_cycle_as_cold():
    a,b=pair();assert current_observed_matches(a,b)['power_cycles_observed']==0

@pytest.mark.parametrize('key,value',[('startup_origin','user_confirmed_power_cycle'),('reboots_issued',1),
    ('power_cycles_observed',1),('expected_boot','old'),('installed_files_sha256',{'boot':'other'})])
def test_inconsistent_observed_rearm_rejected(key,value):
    a,b=pair();b[key]=value
    with pytest.raises(ValueError):current_observed_matches(a,b)
