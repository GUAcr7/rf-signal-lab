import numpy as np
import pytest
from rfsig.rf_ai_calibration import measure_calibration_tone,common_tone_calibration,adapt_calibrated
from rfsig.rf_ai_input import SAMPLE_RATE_HZ,NOMINAL_IF_HZ

def tone(f,phase=.4):return .7*np.exp(1j*(phase+2*np.pi*f*np.arange(65536)/SAMPLE_RATE_HZ))

@pytest.mark.parametrize('offset',[-40000,0,33840,40000])
def test_fractional_tone_fit_and_phase_independent_shared_correction(offset):
    f=NOMINAL_IF_HZ+offset+.37
    c=common_tone_calibration([tone(f),tone(f,.9)])
    assert abs(c['frequency_hz']-f)<1e-6
    frames,meta=adapt_calibrated(tone(f),sample_rate_hz=SAMPLE_RATE_HZ,calibration=c)
    np.testing.assert_allclose(frames,.7*np.exp(.4j),atol=1e-10)
    assert meta['modulation_labels_used'] is False

def test_noisy_single_tone_is_measured_without_a_modulation_label():
    rng=np.random.default_rng(71);x=tone(993840.4)+.003*(rng.normal(size=65536)+1j*rng.normal(size=65536))
    result=measure_calibration_tone(x)
    assert abs(result['frequency_hz']-993840.4)<.2 and result['residual_nmse_db']<-35

@pytest.mark.parametrize('kind',['noise','zero','short','unstable','label-assisted'])
def test_unreliable_or_class_specific_calibration_is_rejected(kind):
    rng=np.random.default_rng(5);x=tone(993840)
    with pytest.raises(ValueError):
        if kind=='noise':measure_calibration_tone(rng.normal(size=65536)+1j*rng.normal(size=65536))
        elif kind=='zero':measure_calibration_tone(x*0)
        elif kind=='short':measure_calibration_tone(x[:100])
        elif kind=='unstable':common_tone_calibration([x,tone(994040)])
        else:
            c=common_tone_calibration([x,x]);c['modulation_labels_used']=True
            adapt_calibrated(x,sample_rate_hz=SAMPLE_RATE_HZ,calibration=c)
