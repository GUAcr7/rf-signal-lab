import numpy as np
import pytest

from rfsig.iq_recording import load_iq_record, save_iq_record


def test_known_iq_round_trip_preserves_values_dtype_and_metadata(tmp_path):
    original = np.array([1 + 2j, -3 + 4j, -1j], dtype=np.complex128)
    directory = tmp_path / "known"
    saved = save_iq_record(directory, original, {"sample_rate_hz": 30_720_000})

    replay, metadata = load_iq_record(directory)
    np.testing.assert_array_equal(replay, original)
    assert replay.dtype == original.dtype
    assert metadata == saved
    assert metadata["sample_count"] == 3
    assert metadata["sample_rate_hz"] == 30_720_000


def test_rejects_modified_sample_file(tmp_path):
    directory = tmp_path / "capture"
    save_iq_record(directory, np.array([1 + 2j]), {})
    with (directory / "iq.npy").open("ab") as file:
        file.write(b"changed")

    with pytest.raises(ValueError, match="SHA256"):
        load_iq_record(directory)


def test_does_not_overwrite_existing_record(tmp_path):
    directory = tmp_path / "capture"
    save_iq_record(directory, np.array([1 + 2j]), {})

    with pytest.raises(FileExistsError):
        save_iq_record(directory, np.array([3 + 4j]), {})


@pytest.mark.parametrize(
    "invalid",
    [np.array([]), np.array([[1 + 2j]]), np.array([1.0]), np.array([np.nan + 1j])],
)
def test_rejects_invalid_iq(tmp_path, invalid):
    with pytest.raises(ValueError):
        save_iq_record(tmp_path / "invalid", invalid, {})
