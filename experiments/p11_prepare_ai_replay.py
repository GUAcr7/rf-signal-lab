"""Build a marked validation-data replay demo; no training or board access."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from shutil import copyfile
from time import perf_counter

import numpy as np

from rfsig.display_classifier import DisplayClassifier, FROZEN_MODEL_SHA256
from rfsig.rx_monitor import RxBlock
from rfsig.stream_monitor import StreamMonitor, verify_stream_archive


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data/p08-synthetic-v1-20261011T053828Z"
MODEL = ROOT / "results/p09-trained-cnn-20261011T055334Z/cnn-model.npz"


def main():
    manifest_path = DATASET / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["source"] == "SYNTHETIC_NOT_REAL_RF"
    rows = [next(r for r in manifest["records"] if r["modulation"] == label and r["split"] == "validation"
                 and r["nominal_snr_db"] == 20) for label in ("BPSK", "QPSK", "16QAM")]
    assert hashlib.sha256(MODEL.read_bytes()).hexdigest() == FROZEN_MODEL_SHA256
    out = ROOT / "results" / datetime.now(timezone.utc).strftime("p11-ai-replay-%Y%m%dT%H%M%S%fZ")
    out.mkdir()
    copyfile(MODEL, out / "cnn-model.npz")
    classifier = DisplayClassifier(out / "cnn-model.npz")
    # The classifier sees only the frame, rate and source kind, never this truth list.
    settings = {"sample_rate_hz": 1000000, "rx_rf_bandwidth_hz": 800000, "rx_lo_hz": 0,
                "gain_control_mode": "not_applicable", "rx_port": "synthetic_baseband",
                "sample_units": "normalized_complex_amplitude", "dataset_split": "validation"}
    monitor = StreamMonitor(settings, out / "session", fft_size=1024, history_frames=96,
                            chunk_frames=8, source_kind="synthetic_test")
    truth, predictions = [], []
    for row in rows:
        path = DATASET / row["file"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row["file_sha256"]
        with np.load(path, allow_pickle=False) as source:
            frames = source["noisy"].copy().reshape(-1, 1024)
        for index, iq in enumerate(frames):
            before = perf_counter()
            # These are file-read host timestamps, never RF acquisition evidence.
            monitor.append(RxBlock(iq, before, perf_counter(), 0., 0.))
            result = classifier.predict(iq, sample_rate_hz=1000000, source_kind="synthetic_test",
                                        block_number=monitor.received)
            assert result["status"] == "synthetic_replay_prediction"
            predictions.append(result)
            truth.append({"block_number": monitor.received, "record_id": row["record_id"], "frame_index": index,
                          "label": row["modulation"], "split": "validation", "nominal_snr_db": 20,
                          "file_sha256": row["file_sha256"]})
    monitor.flush()
    monitor.state, monitor.context_released, monitor.finalized = "saved_synthetic_demo", False, True
    monitor.write_summary()
    verification = verify_stream_archive(monitor.directory)
    verification.update({"purpose": "Display integration demo, not a new independent accuracy evaluation",
                         "board_accessed": False, "rf_transmitted": False, "training_performed": False,
                         "dataset_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                         "model_sha256": FROZEN_MODEL_SHA256,
                         "source_records": [r["record_id"] for r in rows],
                         "predictions_match_demo_labels": sum(a["class_name"] == b["label"] for a,b in zip(predictions,truth,strict=True)),
                         "frames": len(truth)})
    for name, data in (("verification.json", verification), ("expected-labels.json", truth), ("predictions.json", predictions)):
        (out / name).write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False)+"\n", encoding="utf-8")
    command = ('@echo off\nsetlocal\ncd /d "' + str(ROOT) + '"\n'
               '".venv\\Scripts\\python.exe" -X utf8 "host\\stream_monitor_viewer.py" --archive "' + str(out / "session") + '" --model "' + str(out / "cnn-model.npz") + '"\n'
               'if errorlevel 1 pause\nendlocal\n')
    (out / "run-demo.cmd").write_text(command, encoding="utf-8")
    print("AI replay demo:", out)
    print(json.dumps(verification, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
