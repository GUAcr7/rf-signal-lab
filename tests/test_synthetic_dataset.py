from copy import deepcopy
import numpy as np
import pytest
from rfsig.synthetic_dataset import make_record,validate_records,CLASSES

@pytest.mark.parametrize('modulation',CLASSES)
def test_signal_noise_and_frames(modulation):
    r=make_record(modulation,15,0,2)
    assert r.clean.shape==r.noisy.shape==(2048,)
    assert r.clean.dtype==np.complex64 and np.isfinite(r.noisy).all()
    noise=r.noisy.astype(complex)-r.clean.astype(complex)
    snr=10*np.log10(np.mean(abs(r.clean.astype(complex))**2)/np.mean(abs(noise)**2))
    assert abs(snr-r.metadata['measured_record_snr_db'])<1e-10
    assert abs(snr-15)<.5
    np.testing.assert_allclose(np.mean(abs(r.clean.astype(complex))**2),r.metadata['amplitude']**2,rtol=1e-6)

def test_reproducible_independent_sources_and_balanced_conditions():
    rows=[make_record(c,10,14,1) for c in CLASSES]
    repeat=make_record('BPSK',10,14,1)
    np.testing.assert_array_equal(rows[0].noisy,repeat.noisy)
    assert rows[0].metadata==repeat.metadata
    assert len({r.metadata['clean_sha256'] for r in rows})==3
    for field in ['amplitude','phase_rad','cfo_hz','samples_per_symbol','integer_timing_offset']:
        assert len({r.metadata[field] for r in rows})==1
    assert validate_records([r.metadata for r in rows])['records']==3

def test_parent_and_frame_leakage_rejected():
    rows=[make_record('QPSK',20,i,1).metadata for i in [0,14,17]]
    assert validate_records(rows)['unique_frames']==3
    bad=deepcopy(rows);bad[1]['clean_sha256']=bad[0]['clean_sha256']
    with pytest.raises(ValueError,match='parent'):validate_records(bad)
    bad=deepcopy(rows);bad[2]['frame_sha256']=bad[0]['frame_sha256']
    with pytest.raises(ValueError,match='frames'):validate_records(bad)

@pytest.mark.parametrize('args',[('CW',10,0),('BPSK',-5,0),('BPSK',10,20),('BPSK',10,True),('BPSK',10,0,0)])
def test_invalid_condition_rejected(args):
    with pytest.raises(ValueError):make_record(*args)
