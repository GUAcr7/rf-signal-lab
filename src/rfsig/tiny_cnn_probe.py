"""Untrained deterministic operator probe; never a modulation classifier."""
import numpy as np

FRAME = 1024
FEATURES = 8
KERNEL = 5
STRIDE = 2
POSITIONS = (FRAME - KERNEL) // STRIDE + 1


def weights():
    conv = np.array([[[((o*11+i*5+k*3) % 17 - 8)/32
                       for k in range(KERNEL)] for i in range(2)]
                     for o in range(FEATURES)], dtype=np.float32)
    bias = np.array([(o-3)/64 for o in range(FEATURES)], dtype=np.float32)
    dense = np.array([[((c*7+o*3) % 11-5)/16 for o in range(FEATURES)]
                      for c in range(3)], dtype=np.float32)
    dense_bias = np.array([(c-1)/32 for c in range(3)], dtype=np.float32)
    return conv, bias, dense, dense_bias


def infer_counts(counts):
    a = np.asarray(counts)
    if a.shape != (FRAME, 2) or a.dtype.kind not in "iu" or np.any(a < -2048) or np.any(a > 2047):
        raise ValueError("Expected 1024x2 signed 12-bit integer counts")
    x = a.astype(np.float32) / np.float32(2048)
    conv, bias, dense, dense_bias = weights()
    features = np.broadcast_to(bias[:, None], (FEATURES, POSITIONS)).copy()
    for i in range(2):
        for k in range(KERNEL):
            features += conv[:, i, k, None] * x[k:k+POSITIONS*STRIDE:STRIDE, i][None, :]
    np.maximum(features, np.float32(0), out=features)
    pooled = np.zeros(FEATURES, dtype=np.float32)
    for n in range(POSITIONS):
        pooled += features[:, n]
    pooled /= np.float32(POSITIONS)
    logits = dense_bias.copy()
    for o in range(FEATURES):
        logits += dense[:, o] * pooled[o]
    return logits
