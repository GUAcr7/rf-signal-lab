import numpy as np
import pytest

from rfsig.capture_continuity import assess_source_progress


def test_modulo_consistency_never_proves_lossless_adc_time():
    result=assess_source_progress([0,512,1024],[1,1,1],512,2048)
    assert result["status"]=="modulo_consistent"
    assert result["lossless_proven"] is False


def test_a_whole_period_loss_can_produce_byte_identical_received_data():
    rng=np.random.default_rng(2018)
    period=rng.normal(size=2048)+1j*rng.normal(size=2048)
    good=period[(512+np.arange(512))%len(period)]
    skipped=period[(512+2048+np.arange(512))%len(period)]
    np.testing.assert_array_equal(good,skipped)
    result=assess_source_progress([0,512],[.999,.999],512,2048)
    assert result["lossless_proven"] is False


def test_negative_one_is_signed_timing_tolerance_not_a_full_period_gap():
    result=assess_source_progress([100,611],[1,1],512,2048)
    assert result["status"]=="modulo_consistent"
    assert result["boundaries"][0]["extra_advance_modulo_period"]==-1


def test_failed_window_does_not_join_nonadjacent_neighbours():
    result=assess_source_progress([100,None,1124],[1,None,1],512,2048)
    assert result["status"]=="inconclusive"
    assert result["unverified_boundary_count"]==2
    assert result["detected_jump_count"]==0
    assert len(result["boundaries"])==2


def test_low_correlation_is_not_reported_as_a_time_jump():
    result=assess_source_progress([100,1700],[1,.004],512,2048)
    assert result["status"]=="inconclusive"


def test_real_nonperiodic_jump_is_detected():
    result=assess_source_progress([100,900],[1,1],512,2048)
    assert result["detected_jump_count"]==1
    assert result["boundaries"][0]["extra_advance_modulo_period"]==288


def test_one_window_is_insufficient_for_a_boundary_claim():
    assert assess_source_progress([0],[1],512,2048)["status"]=="inconclusive"


@pytest.mark.parametrize("starts,corr,buf,period",[([0],[1,1],512,2048),([2048,0],[1,1],512,2048),
                                                  ([0,512],[1,1],0,2048),([0,512],[1,1],512.5,2048)])
def test_assessment_rejects_invalid_layout(starts,corr,buf,period):
    with pytest.raises(ValueError): assess_source_progress(starts,corr,buf,period)
