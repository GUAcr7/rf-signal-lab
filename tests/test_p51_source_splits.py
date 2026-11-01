from copy import deepcopy
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'experiments'))
from p51_prepare_rf_bank import records,validate_splits

def test_seed_and_session_groups_are_preassigned_not_random_frames():
    rows=records();validate_splits(rows)
    assert [sum(r['role']==k for r in rows) for k in ('train','validation','test')]==[6,3,3]
    assert not any(r['real_RF_acquired'] for r in rows)

@pytest.mark.parametrize('kind',['duplicate-seed','shared-session','old-source','false-RF','wrong-split'])
def test_leaked_or_unacquired_data_cannot_be_marked_as_independent(kind):
    rows=deepcopy(records())
    if kind=='duplicate-seed':rows[-1]['seed']=rows[0]['seed']
    if kind=='shared-session':rows[-1]['planned_capture_session']=rows[0]['planned_capture_session']
    if kind=='old-source':rows[-1]['seed']=20261016
    if kind=='false-RF':rows[-1]['real_RF_acquired']=True
    if kind=='wrong-split':rows[-1]['role']='train'
    with pytest.raises(ValueError):validate_splits(rows)
