"""Provenance/rate gates and label-independent, versioned display predictions."""

import hashlib

import numpy as np
import pytest

from rfsig.display_classifier import DisplayClassifier
from rfsig.trainable_cnn import initialize, forward, patches, preprocess


@pytest.fixture
def classifier(tmp_path):
    path = tmp_path / "reference.npz"
    np.savez(path, **initialize())
    return DisplayClassifier(path, expected_sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def wave():
    return np.exp(2j*np.pi*.03125*np.arange(1024))


def test_display_prediction_matches_frozen_reference_without_reading_labels(classifier):
    result = classifier.predict(wave(), sample_rate_hz=1000000, source_kind="synthetic_test", block_number=7)
    expected = forward(patches(preprocess(wave()[None, :])), classifier.model)[0]
    np.testing.assert_allclose(result["logits"], expected)
    assert result["block_number"] == 7 and result["inference_location"] == "host_PC"
    assert result["class_name"] == result["classes"][int(np.argmax(expected))]
    assert sum(result["softmax_scores"]) == pytest.approx(1)
    assert not result["scores_calibrated"] and not result["real_rf_accuracy_verified"]


@pytest.mark.parametrize("source", ["live_iio_rx_snapshots", "unknown", "saved_real_rx"])
def test_live_or_unknown_input_is_blocked_even_at_matching_sample_rate(classifier, source):
    result = classifier.predict(wave(), sample_rate_hz=1000000, source_kind=source, block_number=1)
    assert result["status"] == "blocked_pending_real_rf_validation" and result["class_name"] is None


@pytest.mark.parametrize("fs", [30720000, 3840000, 999999, float('nan')])
def test_sampling_rate_mismatch_is_not_silently_accepted(classifier, fs):
    result = classifier.predict(wave(), sample_rate_hz=fs, source_kind="synthetic_test", block_number=1)
    assert result["status"] == "blocked_sampling_rate_mismatch"


@pytest.mark.parametrize("iq", [np.zeros(1024, dtype=complex), np.ones(1024), np.zeros(1000, dtype=complex), np.full(1024, np.nan+1j)])
def test_invalid_frames_do_not_fabricate_a_class(classifier, iq):
    result = classifier.predict(iq, sample_rate_hz=1000000, source_kind="synthetic_test", block_number=1)
    assert result["status"] == "rejected_invalid_input" and result["class_name"] is None


def test_modified_model_or_wrong_architecture_is_rejected(tmp_path):
    path = tmp_path / "changed.npz"
    np.savez(path, **initialize())
    with pytest.raises(ValueError, match="hash"):
        DisplayClassifier(path)
    params = initialize()
    params["conv_w"] = np.zeros((2, 2), dtype=np.float32)
    np.savez(path, **params)
    with pytest.raises(ValueError, match="shape"):
        DisplayClassifier(path, hashlib.sha256(path.read_bytes()).hexdigest())
