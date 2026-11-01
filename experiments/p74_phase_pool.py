"""Offline candidate: fixed phase-group logit mean, followed by 3/3 consensus.

No labels, source identity, confidence fallback, or model fitting in inference.
This module is deliberately separate from the installed P70 receiver.
"""
import numpy as np
from rfsig.trainable_cnn import preprocess, patches
from rfsig.cnn_quantization import quantized_forward

PHASE_DEGREES = tuple(range(0, 360, 45))


def phase_pool_logits(frames, quantized):
    x = np.asarray(frames, dtype=np.complex64)
    # Validate and normalize through exactly the existing reference frontend.
    preprocess(x)
    variants = np.concatenate([
        np.asarray(x * np.exp(1j * np.deg2rad(d)), dtype=np.complex64)
        for d in PHASE_DEGREES
    ])
    logits = quantized_forward(patches(preprocess(variants)), quantized)
    return logits.reshape(len(PHASE_DEGREES), len(x), 3).mean(axis=0)


def three_frame_consensus(logits):
    a = np.asarray(logits, dtype=float)
    if a.shape != (3, 3) or not np.isfinite(a).all():
        raise ValueError('Exactly three finite 3-class logits required')
    predictions = a.argmax(axis=1)
    return dict(predictions=predictions.tolist(),
                accepted_class=int(predictions[0]) if np.all(predictions == predictions[0]) else -1)
