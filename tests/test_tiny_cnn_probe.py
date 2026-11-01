import numpy as np
import pytest
from rfsig.tiny_cnn_probe import infer_counts, weights, FRAME, POSITIONS


def independent_double_reference(counts):
    conv,bias,dense,db=weights()
    x=np.asarray(counts,dtype=np.float64)/2048
    windows=np.array([x[n*2:n*2+5].T for n in range(POSITIONS)])
    features=np.maximum(np.einsum('oik,nik->on',conv.astype(float),windows)+bias[:,None],0)
    return dense.astype(float) @ features.mean(axis=1)+db


@pytest.mark.parametrize('seed',[0,1,19])
def test_against_independent_double(seed):
    counts=np.random.default_rng(seed).integers(-2048,2048,(FRAME,2),dtype=np.int16)
    np.testing.assert_allclose(infer_counts(counts),independent_double_reference(counts),rtol=0,atol=2e-6)


def test_zero_input_analytic():
    conv,bias,dense,db=weights()
    np.testing.assert_allclose(infer_counts(np.zeros((FRAME,2),dtype=np.int16)),dense@np.maximum(bias,0)+db,rtol=0,atol=2e-6)
    assert conv.size+bias.size+dense.size+db.size==115


@pytest.mark.parametrize('bad',[np.zeros((FRAME-1,2),dtype=np.int16),np.zeros((FRAME,2)),np.full((FRAME,2),2048,dtype=np.int16)])
def test_reject_invalid_contract(bad):
    with pytest.raises(ValueError): infer_counts(bad)
