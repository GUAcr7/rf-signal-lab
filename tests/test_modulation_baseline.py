import numpy as np
import pytest
from rfsig.modulation_baseline import features,loss_gradient,confusion

def test_features_ignore_constant_phase_scale_and_dc():
    rng=np.random.default_rng(3);x=rng.normal(size=1024)+1j*rng.normal(size=1024)
    np.testing.assert_allclose(features(x),features(3*x*np.exp(.7j)+2-4j),rtol=1e-11,atol=1e-11)

@pytest.mark.parametrize('x',[np.zeros(1024),np.ones(1024),np.full(1024,np.nan),np.ones(100)])
def test_invalid_frame(x):
    with pytest.raises(ValueError):features(x)

def test_gradient_independent_finite_difference():
    rng=np.random.default_rng(7);x=rng.normal(size=(5,3));y=np.array([0,1,2,0,1]);w=rng.normal(size=(3,3))*.1;b=rng.normal(size=3)*.1
    _,dw,db=loss_gradient(x,y,w,b,.01)
    eps=1e-6
    for index in np.ndindex(w.shape):
        plus=w.copy();minus=w.copy();plus[index]+=eps;minus[index]-=eps
        numeric=(loss_gradient(x,y,plus,b,.01)[0]-loss_gradient(x,y,minus,b,.01)[0])/(2*eps)
        assert abs(numeric-dw[index])<1e-7
    for j in range(3):
        plus=b.copy();minus=b.copy();plus[j]+=eps;minus[j]-=eps
        numeric=(loss_gradient(x,y,w,plus,.01)[0]-loss_gradient(x,y,w,minus,.01)[0])/(2*eps)
        assert abs(numeric-db[j])<1e-7

def test_confusion_orientation():
    assert confusion([0,1,2,0],[1,1,0,0]).tolist()==[[1,1,0],[0,1,0],[1,0,0]]
