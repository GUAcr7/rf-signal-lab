"""Small trainable Conv/ReLU/GAP/Dense reference, synthetic-only evaluation."""
import numpy as np

def preprocess(frames):
    x=np.asarray(frames,dtype=np.complex128)
    if x.ndim!=2 or x.shape[1]!=1024 or not len(x) or not np.isfinite(x).all():
        raise ValueError('Expected finite batch of 1024 complex samples')
    x=x-x.mean(axis=1,keepdims=True)
    with np.errstate(over='ignore',invalid='ignore'):
        power=np.mean(abs(x)**2,axis=1,keepdims=True)
    if not np.isfinite(power).all() or np.any(power<=1e-20):raise ValueError('Frame has no usable variance')
    x=x/np.sqrt(power)
    return np.stack((x.real,x.imag),axis=-1).astype(np.float32)

def patches(x):
    a=np.asarray(x)
    if a.ndim!=3 or a.shape[1:]!=(1024,2) or not len(a) or not np.isfinite(a).all():
        raise ValueError('Expected finite batch x 1024 x 2')
    # Flattened order: tap0 I,Q; tap1 I,Q; ... tap4 I,Q.
    return np.stack([a[:,k:k+1020:2,:] for k in range(5)],axis=2).reshape(len(a),510,10)

def initialize(seed=20261011,dtype=np.float32):
    rng=np.random.default_rng(seed)
    return {'conv_w':rng.normal(0,np.sqrt(2/10),(10,8)).astype(dtype),
            'conv_b':np.full(8,.05,dtype=dtype),
            'dense_w':rng.normal(0,np.sqrt(1/8),(8,3)).astype(dtype),
            'dense_b':np.zeros(3,dtype=dtype)}

def forward(p,model):
    z=p@model['conv_w']+model['conv_b']
    h=np.maximum(z,0).mean(axis=1)
    return h@model['dense_w']+model['dense_b']

def loss_gradient(p,y,model,l2=0):
    z=p@model['conv_w']+model['conv_b'];h=np.maximum(z,0).mean(axis=1)
    logits=h@model['dense_w']+model['dense_b'];logits=logits-logits.max(axis=1,keepdims=True)
    ex=np.exp(logits);prob=ex/ex.sum(axis=1,keepdims=True)
    loss=float(np.mean(np.log(ex.sum(axis=1))-logits[np.arange(len(y)),y])+
               .5*l2*(np.sum(model['conv_w']**2)+np.sum(model['dense_w']**2)))
    d=prob.copy();d[np.arange(len(y)),y]-=1;d/=len(y)
    dz=(d@model['dense_w'].T)[:,None,:]/p.shape[1]*(z>0)
    g={'dense_w':h.T@d+l2*model['dense_w'],'dense_b':d.sum(axis=0),
       'conv_w':p.reshape(-1,10).T@dz.reshape(-1,8)+l2*model['conv_w'],
       'conv_b':dz.sum(axis=(0,1))}
    return loss,g
