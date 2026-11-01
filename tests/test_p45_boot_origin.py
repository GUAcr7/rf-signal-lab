import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'experiments'))
from p43_accept_power_on import observed_origin

def evidence():
    markers=['ORIGINAL_BACKUP_VERIFIED boot=new','EMPTY_BINDINGS_VERIFIED','PL_ATTEMPT=1','OVERLAY_ATTEMPT=1','MONITOR_LAUNCH duration_ms=0','PERSISTENT_MONITOR_READY']
    return {'expected_boot':'old'},{'boot_id':'new','init_boot_marker_matches':True,'startup_log':'\n'.join('p43: '+m for m in markers)}

def test_uncaptured_existing_boot_is_never_a_power_cycle():
    e,b=evidence();assert observed_origin(e,b,None,None,'')=='existing_new_boot_power_cycle_not_verified'

@pytest.mark.parametrize('change',['same_boot','missing_marker','wrong_marker_boot'])
def test_invalid_existing_startup_rejected(change):
    e,b=evidence()
    if change=='same_boot':b['boot_id']='old'
    elif change=='missing_marker':b['init_boot_marker_matches']=False
    else:b['startup_log']=b['startup_log'].replace('boot=new','boot=wrong')
    with pytest.raises(ValueError):observed_origin(e,b,None,None,'')

def test_power_cycle_requires_both_human_and_passive_proof():
    e,b=evidence();h={'new_board_powercycled_by_user':True,'old_boot':'old'}
    c=dict(status='passive_window_completed',UART_bytes_sent=0,new_kernel_output_observed=True,P43_ready_marker_observed=True)
    assert observed_origin(e,b,c,h,'ORIGINAL_BACKUP_VERIFIED boot=new')=='user_confirmed_power_cycle'
    for cap,human,text in [(None,h,''),(c,None,''),(dict(c,UART_bytes_sent=1),h,'ORIGINAL_BACKUP_VERIFIED boot=new'),(c,h,'wrong')]:
        with pytest.raises(ValueError):observed_origin(e,b,cap,human,text)
