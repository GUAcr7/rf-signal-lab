"""Frozen CNN for explicitly synthetic 1 MS/s replay, never unvalidated live RX."""

import hashlib
from pathlib import Path

import numpy as np

from rfsig.trainable_cnn import forward, patches, preprocess


FROZEN_MODEL_SHA256 = "cf24285e41c9b113fd05e56498c47292884f3b792a6b097e8fe2afb0a469869b"
CLASSES = ("BPSK", "QPSK", "16QAM")
SHAPES = {"conv_w": (10, 8), "conv_b": (8,), "dense_w": (8, 3), "dense_b": (3,)}


class DisplayClassifier:
    def __init__(self, model_path, expected_sha256=FROZEN_MODEL_SHA256):
        self.path = Path(model_path).resolve()
        self.sha256 = hashlib.sha256(self.path.read_bytes()).hexdigest()
        if self.sha256 != expected_sha256:
            raise ValueError("Model hash differs from the frozen reference")
        with np.load(self.path, allow_pickle=False) as source:
            if set(source.files) != set(SHAPES):
                raise ValueError("Unexpected CNN parameter names")
            self.model = {name: source[name].copy() for name in SHAPES}
        for name, value in self.model.items():
            if value.shape != SHAPES[name] or value.dtype != np.float32 or not np.isfinite(value).all():
                raise ValueError("Unexpected CNN shape, dtype or nonfinite parameter")
            value.flags.writeable = False

    def predict(self, iq, *, sample_rate_hz, source_kind, block_number):
        common = {"model_id": "CNN-115-SYNTHETIC-v1-FP32", "model_sha256": self.sha256,
                  "block_number": int(block_number), "inference_location": "host_PC",
                  "real_rf_accuracy_verified": False, "scores_calibrated": False}
        if source_kind != "synthetic_test":
            return {**common, "status": "blocked_pending_real_rf_validation", "class_name": None}
        if sample_rate_hz != 1000000:
            return {**common, "status": "blocked_sampling_rate_mismatch", "class_name": None}
        values = np.asarray(iq)
        if values.shape != (1024,) or values.dtype.kind != 'c':
            return {**common, "status": "rejected_invalid_input", "class_name": None}
        try:
            logits = forward(patches(preprocess(values[None, :])), self.model)[0]
        except ValueError:
            return {**common, "status": "rejected_invalid_input", "class_name": None}
        logits = np.asarray(logits, dtype=np.float64)
        if logits.shape != (3,) or not np.isfinite(logits).all():
            return {**common, "status": "rejected_invalid_output", "class_name": None}
        weights = np.exp(logits - logits.max())
        scores = weights / weights.sum()
        return {**common, "status": "synthetic_replay_prediction",
                "class_name": CLASSES[int(np.argmax(logits))], "classes": list(CLASSES),
                "logits": logits.tolist(), "softmax_scores": scores.tolist(),
                "note": "Host inference on a saved synthetic frame; not live/ARM RF classification or a calibrated probability."}
