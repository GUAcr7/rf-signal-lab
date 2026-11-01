import importlib.util
from pathlib import Path
import sys
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'experiments'))
from p40_factory_boot import classify_factory_boot, RF_NAMES

LOG='board-init: overlay applied: /lib/firmware/pl.dtbo (attempt 1)\nboard-init: bring-up complete (mode=rf)'


def test_single_warm_boot_is_only_readiness():
    assert classify_factory_boot(LOG,RF_NAMES,'0',False)=='passed_factory_RF_single_apply_warm_boot_only'


def test_logged_ff_is_not_pass():
    assert classify_factory_boot('Unsupported PRODUCT_ID 0xFF',set(),'0',False)=='factory_PRODUCT_ID_FF_observed_no_hot_retry'


@pytest.mark.parametrize('log,names,taint,fb',[
    (LOG,RF_NAMES,'1',False),
    (LOG+'\nOops: bad',RF_NAMES,'0',False),
    (LOG,RF_NAMES,'0',True),
    (LOG,set(),'0',False),
    (LOG+'\nUnsupported PRODUCT_ID 0xFF',RF_NAMES,'0',False),
    (LOG+'\n'+LOG,RF_NAMES,'0',False),
    (LOG+'\nboard-init: FAILED: partial',RF_NAMES,'0',False),
])
def test_fault_or_ambiguous_history_never_passes(log,names,taint,fb):
    with pytest.raises(ValueError):classify_factory_boot(log,names,taint,fb)
