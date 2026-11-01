import numpy as np
import pytest
from rfsig.cnn_quantization import quantized_forward,calibrate
from rfsig.synthetic_dataset import make_record

def test_quantized_mac_independent_integer_loops():
    p=np.array([[[.5,-.6],[1.,.3],[-2.,3.]]])
    q={'input_scale':.1,'conv_weight_scale':.2,'activation_scale':.15,'dense_weight_scale':.3,
       'conv_w':np.array([[2,3],[-4,1]],dtype=np.int8),'conv_b':np.array([4,-1],dtype=np.int32),
       'dense_w':np.array([[1,2,-1],[3,0,2]],dtype=np.int8),'dense_b':np.array([.2,0,-.1])}
    sums=[0,0]
    for row in p[0]:
        ints=[int(np.clip(np.rint(v/.1),-127,127)) for v in row]
        for ch in range(2):
            acc=sum(ints[k]*int(q['conv_w'][k,ch]) for k in range(2))+int(q['conv_b'][ch])
            sums[ch]+=int(np.clip(np.rint(acc*.1*.2/.15),0,127))
    expected=[sum(sums[ch]*int(q['dense_w'][ch,c]) for ch in range(2))*.15*.3/3+q['dense_b'][c] for c in range(3)]
    np.testing.assert_allclose(quantized_forward(p,q)[0],expected,atol=1e-14)

def test_calibration_rejects_validation_sized_input():
    with pytest.raises(ValueError):calibrate(np.zeros((216,510,10)),{})

def test_new_seed_holdout_is_independent_and_reproducible():
    a=make_record('QPSK',15,17,1);b=make_record('QPSK',15,17,1,root_seed=20261012);c=make_record('QPSK',15,17,1,root_seed=20261012)
    assert a.metadata['clean_sha256']!=b.metadata['clean_sha256']
    np.testing.assert_array_equal(b.noisy,c.noisy)
    assert b.metadata['root_seed']==20261012
