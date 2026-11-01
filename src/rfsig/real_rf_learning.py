"""Training-only RF augmentation/calibration and explicit group leakage checks."""
import numpy as np

def validate_frame_groups(records):
    if not records:raise ValueError('empty real RF frame records')
    seeds={};sessions={};hashes=set()
    for row in records:
        role=row['split']
        if role not in ('train','validation','test'):raise ValueError('unknown split')
        for key,table in ((row['seed'],seeds),(row['session'],sessions)):
            if key in table and table[key]!=role:raise ValueError('seed/session crosses splits')
            table[key]=role
        if row['sha256'] in hashes:raise ValueError('duplicate real RF frame')
        hashes.add(row['sha256'])
    return dict(seeds=len(seeds),sessions=len(sessions),frames=len(records))

def augment_training(frames,*,seed,split='train'):
    if split!='train':raise ValueError('augmentation is training-only')
    x=np.asarray(frames,dtype=np.complex128)
    if x.ndim!=2 or x.shape[1]!=1024 or not len(x) or not np.isfinite(x).all():raise ValueError('finite training frames required')
    rng=np.random.default_rng(seed);n=np.arange(1024);result=[]
    for frame in x:
        power=np.mean(abs(frame)**2)
        if power<=1e-20:raise ValueError('empty frame')
        for _ in range(8):
            phase=rng.uniform(-np.pi,np.pi);frequency=rng.uniform(-3000,3000)
            noise=(rng.normal(size=1024)+1j*rng.normal(size=1024))*np.sqrt(power/2000)
            result.append(frame*np.exp(1j*(phase+2*np.pi*frequency*n/1920000))+noise)
    return np.asarray(result,dtype=np.complex64)

def calibrate_real_training(patches,model,*,split='train'):
    if split!='train':raise ValueError('quantizer calibration is training-only')
    p=np.asarray(patches)
    if p.ndim!=3 or p.shape[1:]!=(510,10) or not len(p) or not np.isfinite(p).all():raise ValueError('finite training patches required')
    activation=np.maximum(p@model['conv_w']+model['conv_b'],0)
    q=dict(input_scale=float(max(np.quantile(abs(p),.999)/127,1e-8)),
        conv_weight_scale=float(max(abs(model['conv_w']).max()/127,1e-8)),
        activation_scale=float(max(np.quantile(activation,.999)/127,1e-8)),
        dense_weight_scale=float(max(abs(model['dense_w']).max()/127,1e-8)))
    q['conv_w']=np.clip(np.rint(model['conv_w'].astype(float)/q['conv_weight_scale']),-127,127).astype(np.int8)
    q['dense_w']=np.clip(np.rint(model['dense_w'].astype(float)/q['dense_weight_scale']),-127,127).astype(np.int8)
    bias=np.rint(model['conv_b'].astype(float)/(q['input_scale']*q['conv_weight_scale']))
    if not np.isfinite(bias).all() or np.any(abs(bias)>2**30):raise ValueError('invalid quantized bias')
    q['conv_b']=bias.astype(np.int32);q['dense_b']=model['dense_b'].copy()
    return q
