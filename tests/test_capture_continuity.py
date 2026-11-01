import numpy as np
import pytest

from rfsig.capture_continuity import align_periodic_reference,modulo_gaps
from rfsig.tx_waveforms import make_tx_waveform


@pytest.mark.parametrize("name",["BPSK","QPSK","16QAM"])
def test_known_source_fit_recovers_delay_frequency_and_gain_without_decisions(name):
    waveform=make_tx_waveform(name,sample_rate_hz=128000,samples_per_symbol=8,
                              symbol_count=1024,seed=122,offset_hz=0,digital_peak_counts=256)
    ref=waveform.iq
    position=7813  # Cross the end of the cyclic reference.
    n=np.arange(1024)
    rng=np.random.default_rng(17)
    clean=ref[(position+n)%len(ref)]*.7*np.exp(1j*(.8+2*np.pi*1213*n/128000))
    received=clean+.05*(rng.normal(size=len(n))+1j*rng.normal(size=len(n)))
    fit=align_periodic_reference(received,ref,128000,1210)
    assert fit.source_start==position
    assert fit.frequency_hz==pytest.approx(1213,abs=.05)
    assert fit.correlation>.999
    assert fit.nmse_db < -55
    assert abs(fit.gain)==pytest.approx(.7,rel=.001)


def test_independent_clean_buffers_can_have_a_discontinuous_join():
    rng=np.random.default_rng(3)
    ref=rng.normal(size=2048)+1j*rng.normal(size=2048)
    fits=[]
    for start in (1700,169):  # 512 contiguous samples would end at position 164.
        x=ref[(start+np.arange(512))%len(ref)]*np.exp(.3j)
        fits.append(align_periodic_reference(x,ref,100000,0))
    assert all(f.nmse_db < -100 for f in fits)
    assert modulo_gaps([f.source_start for f in fits],512,len(ref)).tolist()==[5]


def test_wrong_reference_is_not_silently_reported_as_a_match():
    rng=np.random.default_rng(20)
    ref=rng.normal(size=2048)+1j*rng.normal(size=2048)
    x=rng.normal(size=512)+1j*rng.normal(size=512)
    fit=align_periodic_reference(x,ref,100000,0,max_refine_hz=50000)
    assert fit.correlation < .3
    assert fit.nmse_db > 0


@pytest.mark.parametrize("bad",[[],np.zeros(64),np.ones((8,8)),np.full(64,np.nan)])
def test_reference_alignment_rejects_invalid_samples(bad):
    with pytest.raises(ValueError):
        align_periodic_reference(bad,np.ones(128),100000,0)


def test_whole_lost_period_is_deliberately_ambiguous():
    assert modulo_gaps([0,512],512,2048).tolist()==[0]
    # A jump of an entire TX period produces identical source positions.
    assert modulo_gaps([0,512+2048],512,2048).tolist()==[0]


def test_modulo_gaps_rejects_invalid_inputs():
    with pytest.raises(ValueError):
        modulo_gaps([1.2,2.2],4,16)
    with pytest.raises(ValueError):
        modulo_gaps([1,2],0,16)
