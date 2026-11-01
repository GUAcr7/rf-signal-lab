import numpy as np
import pytest

from rfsig.sparse_continuity import StridedReferenceMatcher
from rfsig.tx_waveforms import make_tx_waveform
from rfsig.capture_continuity import assess_source_progress


@pytest.fixture(scope="module")
def reference():
    tx=make_tx_waveform("BPSK",sample_rate_hz=30720000,samples_per_symbol=128,
                        symbol_count=128,seed=731,offset_hz=0,digital_peak_counts=256)
    return tx.iq


@pytest.mark.parametrize("start",[0,3,7,16379])
def test_stride_phase_and_period_wrap_are_resolved_in_raw_sample_units(reference,start):
    rng=np.random.default_rng(33)
    index=np.arange(1024)*8
    target=reference[(start+index)%len(reference)]
    capture=target*np.exp(2j*np.pi*994000*index/30720000+.7j)
    capture+=.0001*(rng.normal(size=len(index))+1j*rng.normal(size=len(index)))
    result=StridedReferenceMatcher(reference,8).align(capture,30720000,994035)
    assert result.source_start==start
    assert result.frequency_hz==pytest.approx(994000,abs=.1)
    assert result.correlation>.99999


def test_known_source_jump_survives_sparse_diagnostic(reference):
    matcher=StridedReferenceMatcher(reference,8)
    starts=[123,123,(123+5000)%len(reference)]  # DMA 65536 is four reference periods here.
    fits=[matcher.align(reference[(start+np.arange(1024)*8)%len(reference)],30720000,0) for start in starts]
    assessment=assess_source_progress([f.source_start for f in fits],[f.correlation for f in fits],65536,len(reference))
    assert assessment["detected_jump_count"]==1
    assert assessment["lossless_proven"] is False


def test_unrelated_noise_does_not_get_high_match_confidence(reference):
    rng=np.random.default_rng(991)
    samples=rng.normal(size=1024)+1j*rng.normal(size=1024)
    try:
        fit=StridedReferenceMatcher(reference,8).align(samples,30720000,0)
    except ValueError:
        return
    assert fit.correlation<.99


@pytest.mark.parametrize("stride",[0,3,True,1.5])
def test_invalid_stride_is_rejected(reference,stride):
    with pytest.raises(ValueError):
        StridedReferenceMatcher(reference,stride)
