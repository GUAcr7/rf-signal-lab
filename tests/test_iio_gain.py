import pytest

from rfsig.iio_runtime import parse_iio_gain_db


@pytest.mark.parametrize("raw,expected", [("-10.000000 dB", -10.), ("71.000000 dB", 71.),
    ("-40", -40.), ("0.0", 0.), (" -0.25 dB\n", -.25), ("1e-2 dB", .01)])
def test_actual_gain_representation_and_numeric_fixtures(raw, expected):
    assert parse_iio_gain_db(raw) == expected


@pytest.mark.parametrize("raw", ["-10 dBm", "10dB", "10 dB junk", "nan dB", "inf", "1e309 dB",
    "", None, 10, "dB -10", "10 Hz", "1 2 dB"])
def test_unknown_units_and_invalid_numbers_are_rejected(raw):
    with pytest.raises(ValueError): parse_iio_gain_db(raw)
