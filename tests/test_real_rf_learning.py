import numpy as np
import pytest
from rfsig.real_rf_learning import validate_frame_groups,augment_training,calibrate_real_training
from rfsig.trainable_cnn import preprocess,patches,initialize
from rfsig.cnn_quantization import quantized_forward

def rows():return [dict(seed=1,session='a',split='train',sha256='x'),dict(seed=2,session='b',split='validation',sha256='y')]
def test_grouped_splits_and_duplicate_bytes_checked():
    assert validate_frame_groups(rows())['seeds']==2
    for field,value in [('seed',1),('session','a'),('sha256','x')]:
        r=rows();r[1][field]=value
        with pytest.raises(ValueError):validate_frame_groups(r)

def frame():return np.exp(1j*np.arange(1024)*.1)[None,:]
def test_augmentation_is_reproducible_and_parent_count_explicit():
    a=augment_training(frame(),seed=1);b=augment_training(frame(),seed=1)
    assert a.shape==(8,1024) and np.array_equal(a,b)
    assert not np.array_equal(a[0],a[1])

@pytest.mark.parametrize('role',['validation','test'])
def test_validation_and_test_cannot_calibrate_or_augment(role):
    with pytest.raises(ValueError):augment_training(frame(),seed=1,split=role)
    with pytest.raises(ValueError):calibrate_real_training(patches(preprocess(frame())),initialize(),split=role)

def test_calibration_supports_real_group_size_without_fake_1008_count():
    p=patches(preprocess(augment_training(frame(),seed=2)));q=calibrate_real_training(p,initialize())
    logits=quantized_forward(p,q)
    assert logits.shape==(8,3) and np.isfinite(logits).all()

@pytest.mark.parametrize('bad',[np.zeros((1,1024)),np.full((1,1024),np.nan),np.zeros((1,100))])
def test_unusable_training_frames_rejected(bad):
    with pytest.raises(ValueError):augment_training(bad,seed=1)
