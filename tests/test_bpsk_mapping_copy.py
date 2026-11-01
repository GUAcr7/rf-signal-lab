import numpy as np
import pytest

from rfsig import map_bpsk


def test_maps_hand_calculated_sequence() -> None:
    actual = map_bpsk([1, 0, 0, 1])
    expected = np.array([-1.0, 1.0, 1.0, -1.0])

    np.testing.assert_array_equal(actual, expected)
    assert actual.shape == (4,)
    assert actual.dtype == np.float64


@pytest.mark.parametrize(
    ("bits", "expected"),
    [
        ([0, 0, 0], [1.0, 1.0, 1.0]),
        ([1, 1, 1], [-1.0, -1.0, -1.0]),
        ([0, 1, 0, 1], [1.0, -1.0, 1.0, -1.0]),
    ],
)
def test_maps_basic_patterns(bits: list[int], expected: list[float]) -> None:
    np.testing.assert_array_equal(map_bpsk(bits), expected)


@pytest.mark.parametrize(
    "invalid_bits",
    [
        [],
        [0, 2, 1],
        [[0, 1], [1, 0]],
    ],
)
def test_rejects_invalid_input(invalid_bits: list[object]) -> None:
    with pytest.raises(ValueError):
        map_bpsk(invalid_bits)
