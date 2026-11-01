import numpy as np
import pytest
from rfsig.rf_ai_input import adapt_dma_block,anti_alias_taps,SAMPLE_RATE_HZ,NOMINAL_IF_HZ


def adapt(x,**kw):
    return adapt_dma_block(x,sample_rate_hz=kw.get('fs',SAMPLE_RATE_HZ),nominal_if_hz=kw.get('offset',NOMINAL_IF_HZ))


def test_fir_passband_and_alias_stopband_meet_frozen_design_limits():
    h=anti_alias_taps();np.testing.assert_allclose(h,h[::-1],atol=1e-16)
    assert abs(h.sum()-1)<1e-14
    n=np.arange(len(h))
    def response(f):return abs(np.exp(-2j*np.pi*np.asarray(f)[:,None]*n/SAMPLE_RATE_HZ)@h)
    assert np.max(abs(20*np.log10(response(np.linspace(0,200000,101)))))<.02
    assert np.max(response(np.linspace(960000,SAMPLE_RATE_HZ/2,4001)))<1e-4


@pytest.mark.parametrize('residual',[-120000,0,120000])
def test_known_frequency_amplitude_phase_and_input_coordinates_survive(residual):
    n=np.arange(65536);x=.7*np.exp(1j*(.4+2*np.pi*(NOMINAL_IF_HZ+residual)*n/SAMPLE_RATE_HZ))
    frames,meta=adapt(x)
    assert frames.shape==(3,1024) and meta['trailing_output_samples_discarded']==992
    expected=.7*np.exp(1j*(.4+2*np.pi*residual*(256+np.arange(3072)*16)/SAMPLE_RATE_HZ))
    np.testing.assert_allclose(frames.ravel(),expected,rtol=3e-5,atol=3e-5)
    assert meta['frame_first_input_center']==[256,16640,33024]


def test_aliasing_interferer_is_filtered_before_downsampling():
    n=np.arange(65536)
    x=np.exp(2j*np.pi*(NOMINAL_IF_HZ+1_920_000)*n/SAMPLE_RATE_HZ)
    frames,_=adapt(x)
    assert np.max(abs(frames))<1e-4
    assert np.max(abs(x[::16]))>.99  # direct slicing would alias it to DC.


def test_buffers_are_independent_no_previous_tail_can_contaminate_next():
    n=np.arange(65536);a=np.exp(2j*np.pi*NOMINAL_IF_HZ*n/SAMPLE_RATE_HZ)
    f,_=adapt(a)
    adapt(np.full_like(a,100))
    g,_=adapt(a)
    np.testing.assert_array_equal(f,g)


@pytest.mark.parametrize('kind',['empty','short','nan','matrix','wrong-rate','wrong-IF','boolean-rate'])
def test_unknown_or_invalid_acquisition_cannot_silently_use_this_adapter(kind):
    n=np.arange(65536);x=np.exp(2j*np.pi*NOMINAL_IF_HZ*n/SAMPLE_RATE_HZ);kw={}
    if kind=='empty':x=x[:0]
    if kind=='short':x=x[:200]
    if kind=='nan':x[3]=np.nan
    if kind=='matrix':x=x.reshape(2,-1)
    if kind=='wrong-rate':kw['fs']=1_000_000
    if kind=='wrong-IF':kw['offset']=0
    if kind=='boolean-rate':kw['fs']=True
    with pytest.raises(ValueError):adapt(x,**kw)
