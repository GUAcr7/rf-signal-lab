"""Lossless storage and checked replay of a short complex I/Q capture."""

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray


SCHEMA = "rfsig.iq_capture.v1"
SAMPLE_FILE = "iq.npy"
METADATA_FILE = "metadata.json"


def _file_sha256(path: Path) -> str:
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def _check_iq(iq: NDArray[Any]) -> None:
    if iq.ndim != 1 or iq.size == 0 or iq.dtype.kind != "c":
        raise ValueError("I/Q must be a nonempty one-dimensional complex array")
    if not np.isfinite(iq).all():
        raise ValueError("I/Q contains non-finite values")


def save_iq_record(
    directory: str | Path, iq: NDArray[Any], metadata: dict[str, Any]
) -> dict[str, Any]:
    """Create a new record directory; never overwrite a previous capture."""
    array = np.asarray(iq)
    _check_iq(array)
    if not isinstance(metadata, dict):
        raise TypeError("metadata must be a dictionary")

    target = Path(directory)
    target.mkdir(parents=True, exist_ok=False)
    sample_path = target / SAMPLE_FILE
    np.save(sample_path, array, allow_pickle=False)

    saved_metadata = dict(metadata)
    saved_metadata.update(
        {
            "schema": SCHEMA,
            "sample_file": SAMPLE_FILE,
            "sample_count": int(array.size),
            "sample_dtype": str(array.dtype),
            "sample_sha256": _file_sha256(sample_path),
        }
    )
    (target / METADATA_FILE).write_text(
        json.dumps(saved_metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return saved_metadata


def load_iq_record(directory: str | Path) -> tuple[NDArray[Any], dict[str, Any]]:
    """Reload a record and reject mismatched or modified sample data."""
    target = Path(directory)
    metadata = json.loads((target / METADATA_FILE).read_text(encoding="utf-8"))
    if not isinstance(metadata, dict) or metadata.get("schema") != SCHEMA:
        raise ValueError("I/Q metadata schema is missing or unsupported")
    if metadata.get("sample_file") != SAMPLE_FILE:
        raise ValueError("I/Q sample filename is unexpected")

    sample_path = target / SAMPLE_FILE
    if _file_sha256(sample_path) != metadata.get("sample_sha256"):
        raise ValueError("I/Q sample file SHA256 does not match metadata")

    iq = np.load(sample_path, allow_pickle=False)
    if not isinstance(iq, np.ndarray):
        raise ValueError("I/Q sample file is not a NumPy array")
    _check_iq(iq)
    if iq.size != metadata.get("sample_count") or str(iq.dtype) != metadata.get(
        "sample_dtype"
    ):
        raise ValueError("I/Q sample count or dtype does not match metadata")
    return iq, metadata
