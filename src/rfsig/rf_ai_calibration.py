"""One common controlled-session IF calibration from an independent single tone.

No modulation labels or classifier scores are inputs. This is not blind carrier
recovery for arbitrary unknown signals, nor absolute RF frequency calibration.
"""
import numpy as np
from .rf_ai_input import SAMPLE_RATE_HZ,NOMINAL_IF_HZ,adapt_dma_block


def measure_calibration_tone(iq):
    x=np.asarray(iq,dtype=np.complex128)
    if x.shape!=(65536,) or not np.isfinite(x).all():raise ValueError('complete finite calibration DMA block required')
    n=np.arange(len(x),dtype=float);freq=np.fft.fftfreq(len(x),1/SAMPLE_RATE_HZ)
    region=np.flatnonzero(abs(freq-NOMINAL_IF_HZ)<=50000)
    spectrum=np.fft.fft(x*np.hanning(len(x)))
    coarse=float(freq[region[np.argmax(abs(spectrum[region]))]])
    z=x*np.exp(-2j*np.pi*coarse*n/SAMPLE_RATE_HZ)
    phase=np.unwrap(np.angle(z));centered=n-n.mean()
    slope=np.dot(centered,phase-phase.mean())/np.dot(centered,centered)
    frequency=coarse+slope*SAMPLE_RATE_HZ/(2*np.pi)
    y=x*np.exp(-2j*np.pi*frequency*n/SAMPLE_RATE_HZ);gain=y.mean()
    power=abs(gain)**2;residual=float(np.mean(abs(y-gain)**2))
    nmse=10*np.log10(max(residual/max(power,1e-30),1e-30))
    if not np.isfinite(frequency) or abs(frequency-NOMINAL_IF_HZ)>50000 or not power>0 or nmse>-20:
        raise ValueError('known single-tone fit rejected; calibration unavailable')
    return dict(frequency_hz=float(frequency),residual_nmse_db=float(nmse),nominal_IF_hz=NOMINAL_IF_HZ)


def common_tone_calibration(blocks):
    rows=[measure_calibration_tone(x) for x in blocks]
    if len(rows)<2:raise ValueError('multiple independent returned tone blocks required')
    f=np.array([r['frequency_hz'] for r in rows])
    if np.ptp(f)>100:raise ValueError('unstable tone calibration; do not classify')
    return dict(status='known_tone_common_IF_calibrated',frequency_hz=float(np.median(f)),
        nominal_residual_hz=float(np.median(f)-NOMINAL_IF_HZ),spread_hz=float(np.ptp(f)),blocks=rows,
        shared_across_modulation_classes=True,modulation_labels_used=False,absolute_RF_calibrated=False)


def adapt_calibrated(iq,*,sample_rate_hz,calibration):
    if (calibration.get('status')!='known_tone_common_IF_calibrated'
        or calibration.get('shared_across_modulation_classes') is not True
        or calibration.get('modulation_labels_used') is not False):raise ValueError('shared tone-only calibration required')
    frequency=calibration['frequency_hz']
    if not np.isfinite(frequency) or abs(frequency-NOMINAL_IF_HZ)>50000:raise ValueError('calibrated IF outside controlled range')
    x=np.asarray(iq,dtype=np.complex128)
    if x.ndim!=1:raise ValueError('one DMA block required')
    x=x*np.exp(-2j*np.pi*(frequency-NOMINAL_IF_HZ)*np.arange(len(x))/SAMPLE_RATE_HZ)
    frames,metadata=adapt_dma_block(x,sample_rate_hz=sample_rate_hz,nominal_if_hz=NOMINAL_IF_HZ)
    metadata.update(common_tone_IF_hz=frequency,modulation_labels_used=False)
    return frames,metadata
