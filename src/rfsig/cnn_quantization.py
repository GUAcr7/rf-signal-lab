"""Train-only calibrated INT8 MAC reference; float rescaling/output retained."""
import numpy as np

def calibrate(training_patches,model):
    p=np.asarray(training_patches)
    if p.shape!=(1008,510,10) or not np.isfinite(p).all():raise ValueError('Expected 1008 training frames only')
    activation=np.maximum(p@model['conv_w']+model['conv_b'],0)
    q={'input_scale':float(max(np.quantile(abs(p),.999)/127,1e-8)),
       'conv_weight_scale':float(max(abs(model['conv_w']).max()/127,1e-8)),
       'activation_scale':float(max(np.quantile(activation,.999)/127,1e-8)),
       'dense_weight_scale':float(max(abs(model['dense_w']).max()/127,1e-8))}
    q['conv_w']=np.clip(np.rint(model['conv_w'].astype(float)/q['conv_weight_scale']),-127,127).astype(np.int8)
    q['dense_w']=np.clip(np.rint(model['dense_w'].astype(float)/q['dense_weight_scale']),-127,127).astype(np.int8)
    bias=np.rint(model['conv_b'].astype(float)/(q['input_scale']*q['conv_weight_scale']))
    if np.any(abs(bias)>2**30):raise ValueError('Quantized bias too large')
    q['conv_b']=bias.astype(np.int32);q['dense_b']=model['dense_b'].copy()
    return q

def quantized_forward(p,q):
    pi=np.clip(np.rint(np.asarray(p,dtype=float)/q['input_scale']),-127,127).astype(np.int32)
    z=pi@q['conv_w'].astype(np.int32)+q['conv_b']
    ai=np.clip(np.rint(z.astype(float)*(q['input_scale']*q['conv_weight_scale']/q['activation_scale'])),0,127).astype(np.int32)
    summed=ai.sum(axis=1,dtype=np.int32)
    accum=summed@q['dense_w'].astype(np.int32)
    return accum.astype(float)*(q['activation_scale']*q['dense_weight_scale']/p.shape[1])+q['dense_b'].astype(float)
