import numpy as np
import pytest

from rfsig.iq_io import load_iq_csv


def test_reads_known_iq_pairs_and_ignores_empty_fields(tmp_path):
    csv_file = tmp_path / "iq.csv"
    csv_file.write_text("-212, -78, \n0, 2047, \n\n", encoding="utf-8")

    actual = load_iq_csv(csv_file)

    assert actual.shape == (2, 2)
    assert actual.dtype == np.int16
    np.testing.assert_array_equal(actual, [[-212, -78], [0, 2047]])


@pytest.mark.parametrize("content", [
    "",
    "1, 2, 3\n",
    "x, 2, \n",
    "32768, 0, \n",
])
def test_rejects_empty_or_invalid_data(tmp_path, content):
    csv_file = tmp_path / "bad.csv"
    csv_file.write_text(content, encoding="utf-8")

    with pytest.raises(ValueError):
        load_iq_csv(csv_file)
