"""Refuse unsafe requests and insufficient cleanup evidence before live use."""
from pathlib import Path
import sys
import threading
import pytest
sys.path.insert(0,str(Path(__file__).parents[1]/'host'))
import source_screen_rf as rf

@pytest.mark.parametrize('name,seconds',[('shell; reboot',15),('BPSK',15),('bpsk',7),('qam16',61),('tone',True),('qpsk',15.5)])
def test_fixed_presets_and_integer_duration_only(name,seconds):
    with pytest.raises(ValueError):rf.validate_request(name,seconds)

@pytest.mark.parametrize('signal',['tone','bpsk','qpsk','qam16'])
def test_validated_presets(signal):rf.validate_request(signal,15)

def test_cancelled_before_launch_does_not_touch_boards():
    class Forbidden:
        def status(self):pytest.fail('Board touched after cancellation')
    cancel=threading.Event();cancel.set()
    with pytest.raises(rf.Cancelled):rf.precheck(Forbidden(),'bpsk',15,cancel)

GOOD='DDS_ZERO_SOURCE_READBACK=PASS\nTX_CLEANUP buffer_released=true rf_settings_written=false status=0\n'

@pytest.mark.parametrize('code,text',[(1,GOOD),(None,GOOD),(0,''),(0,GOOD.replace('true','false')),
                                    (0,GOOD.replace('PASS','FAILED')),(0,GOOD.replace('status=0','status=01'))])
def test_stop_requires_native_cleanup_and_zero_readback_and_exit(code,text):
    assert not rf.cleanup_proven(text,code)

def test_clean_stop_proof():assert rf.cleanup_proven(GOOD,0)

def test_detached_receipt_is_exactly_bound_to_job_boot_preset_and_child():
    receipt=dict(schema='rfsig.source_job.v1',nonce='abcd1234',boot_id='boot',signal='bpsk',seconds=15,
                 identity_valid=True,child_reaped=True,child_pid=123,start_ticks='1234',exit_code=0)
    assert rf.accepted_receipt(receipt,'abcd1234','boot','bpsk',15)
    for patch in ({'nonce':'old'},{'boot_id':'old'},{'signal':'qpsk'},{'seconds':30},
                  {'identity_valid':False},{'child_reaped':False},{'child_pid':True},{'start_ticks':''},{'exit_code':None}):
        assert not rf.accepted_receipt({**receipt,**patch},'abcd1234','boot','bpsk',15)
