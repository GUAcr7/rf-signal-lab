"""Same-boot provenance must be retained when reusing a cold-boot P42 ELF."""
import copy
import json
from pathlib import Path
import sys
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'experiments'))
from p32_session import ROOT
from p46_known_panel import accepted_cold_clock


def clock():
    return json.loads((ROOT/'results/p43-cold-clock-20261022T105246Z/report.json').read_text('utf-8'))


def test_recorded_cold_clock_chain_is_accepted():
    c=clock()
    accepted_cold_clock(c,c['boot_id'])


@pytest.mark.parametrize('change',('boot','warm','trial_hash','readback_hash','rate'))
def test_cold_gate_rejects_stale_or_changed_evidence(change):
    c=copy.deepcopy(clock());boot=c['boot_id']
    if change=='boot':c['boot_id']='00000000-0000-0000-0000-000000000000'
    elif change=='warm':c['host_reboots_issued']=1
    elif change=='trial_hash':c['trial_sha256']='0'*64
    elif change=='readback_hash':c['readback_sha256']='0'*64
    else:c['decoded']['software_matches_prediction_within_1kHz']=False
    with pytest.raises(ValueError):accepted_cold_clock(c,boot)
