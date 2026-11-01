import numpy as np
import pytest
from rfsig.trainable_cnn import preprocess,patches,initialize,forward,loss_gradient

def test_preprocessing_independent_and_dc_amplitude():
    rng=np.random.default_rng(8);x=rng.normal(size=(2,1024))+1j*rng.normal(size=(2,1024))
    out=preprocess(x);ref=x-x.mean(axis=1,keepdims=True);ref/=np.sqrt(np.mean(abs(ref)**2,axis=1,keepdims=True))
    np.testing.assert_allclose(out[...,0]+1j*out[...,1],ref,atol=2e-7)
    np.testing.assert_allclose(preprocess(3*x+4+2j),out,atol=2e-7)

def test_window_and_forward_independent_scalar():
    rng=np.random.default_rng(9);x=rng.normal(size=(1,1024,2));p=patches(x);model=initialize(dtype=np.float64)
    pooled=np.zeros(8)
    for t in range(510):
        out=model['conv_b'].copy()
        for k in range(5):
            for ch in range(2):out+=x[0,2*t+k,ch]*model['conv_w'][2*k+ch]
        pooled+=np.maximum(out,0)/510
    expected=pooled@model['dense_w']+model['dense_b']
    np.testing.assert_allclose(forward(p,model)[0],expected,atol=1e-13)
    assert p.shape==(1,510,10)

@pytest.mark.parametrize('name,index',[('conv_w',(3,4)),('conv_b',(2,)),('dense_w',(3,1)),('dense_b',(2,))])
def test_gradient_independent_finite_difference(name,index):
    rng=np.random.default_rng(20);p=rng.normal(size=(3,7,10));y=np.array([0,1,2]);model=initialize(dtype=np.float64)
    _,gradient=loss_gradient(p,y,model,.003);original=model[name][index];epsilon=1e-6
    model[name][index]=original+epsilon;plus=loss_gradient(p,y,model,.003)[0]
    model[name][index]=original-epsilon;minus=loss_gradient(p,y,model,.003)[0]
    np.testing.assert_allclose(gradient[name][index],(plus-minus)/(2*epsilon),atol=3e-9)

@pytest.mark.parametrize('bad',[np.zeros((1,1024)),np.ones((1,1024))*np.nan,np.ones((1,1023))])
def test_invalid_input(bad):
    with pytest.raises(ValueError):preprocess(bad)

def test_overflowing_power_is_rejected():
    x=np.zeros((1,1024),dtype=complex);x[0,0]=1e300
    with pytest.raises(ValueError):preprocess(x)
