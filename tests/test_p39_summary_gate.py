import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'experiments'))
from p39_run_latest_panel import validate_summary


def summary():
    return dict(schema='rfsig.latest_panel.v1',status='pass',reason='duration_complete',
        duration_ms_requested=3000,UI_interval_ms_requested=500,worker_started=True,worker_joined=True,
        buffer_created=True,buffer_released=True,context_released=True,cleanup_unconfirmed=False,
        RF_before_valid=True,RF_after_matches=True,RF_attributes_written=False,TX_API_loaded=False,
        lossless_proven=False,ADC_gaps='unknown',analyse_only=False,prefix_frames=8192,
        frames_per_refill=65536,source_format='le:S12/16>>0',refill_error=0,
        published_prefixes=100,consumed_prefixes=6,last_display_sequence=99,
        UI_overwritten_prefixes=93,pending_prefixes_at_stop=1,display_updates=6,
        retained_prefix_bytes=32768,elapsed_software_s=3.01)


def test_overwritten_UI_prefixes_are_explicitly_accepted_without_losslessness_claim():
    assert validate_summary(summary(),3000,500)['UI_overwritten_prefixes']==93


@pytest.mark.parametrize('key,value',[('UI_overwritten_prefixes',0),('worker_joined',False),
    ('RF_after_matches',False),('display_updates',7),('lossless_proven',True),
    ('retained_prefix_bytes',262144),('last_display_sequence',101),('elapsed_software_s',2.9)])
def test_false_completion_or_inconsistent_accounting_rejected(key,value):
    s=summary();s[key]=value
    with pytest.raises(ValueError):validate_summary(s,3000,500)
