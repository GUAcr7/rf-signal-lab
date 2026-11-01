"""Traditional feature + linear-softmax synthetic baseline; no RF detection."""
import numpy as np

FEATURE_NAMES=('mean_radius','third_radius_moment','fourth_radius_moment','sixth_radius_moment',
               'radius_q10','radius_q50','radius_q90','radius_q99','abs_second_complex_moment',
               'abs_fourth_complex_moment','lag1_corr','lag2_corr','lag4_corr','lag1_squared_corr')

def features(frame):
    x=np.asarray(frame,dtype=np.complex128)
    if x.shape!=(1024,) or not np.isfinite(x).all():raise ValueError('Expected finite 1024-complex-sample frame')
    x=x-np.mean(x);power=float(np.mean(abs(x)**2))
    if not np.isfinite(power) or power<=1e-20:raise ValueError('Frame has no usable variance')
    x=x/np.sqrt(power);r=abs(x)
    q=np.quantile(r,[.1,.5,.9,.99])
    f=[np.mean(r),np.mean(r**3),np.mean(r**4),np.mean(r**6),*q,
       abs(np.mean(x*x)),abs(np.mean(x**4)),
       *[abs(np.mean(x[k:]*np.conj(x[:-k]))) for k in [1,2,4]],
       abs(np.mean(x[1:]**2*np.conj(x[:-1]**2)))]
    result=np.array(f,dtype=float)
    if not np.isfinite(result).all():raise ValueError('Nonfinite feature')
    return result

def loss_gradient(x,y,w,b,l2):
    logits=x@w+b;logits-=logits.max(axis=1,keepdims=True)
    exp=np.exp(logits);prob=exp/exp.sum(axis=1,keepdims=True)
    loss=float(np.mean(np.log(exp.sum(axis=1))-logits[np.arange(len(y)),y])+.5*l2*np.sum(w*w))
    delta=prob.copy();delta[np.arange(len(y)),y]-=1;delta/=len(y)
    return loss,x.T@delta+l2*w,delta.sum(axis=0)

def confusion(truth,prediction):
    m=np.zeros((3,3),dtype=int)
    for t,p in zip(truth,prediction):m[t,p]+=1
    return m
