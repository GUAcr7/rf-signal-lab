"""BPSK golden-reference functions introduced in Level 0."""

from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray


def map_bpsk(bits: Sequence[int] | NDArray[np.integer]) -> NDArray[np.float64]:
    """Map a one-dimensional 0/1 sequence to +1/-1 BPSK symbols.

    This project uses the convention 0 -> +1 and 1 -> -1.
    The returned values are symbol coefficients, not sampled carrier waveforms.

    Raises:
        ValueError: If the input is empty, is not one-dimensional, or contains
            a value other than 0 or 1.
    """
    bit_array = np.asarray(bits)

    if bit_array.ndim != 1:
        raise ValueError("bits must be a one-dimensional sequence")
    if bit_array.size == 0:
        raise ValueError("bits must not be empty")
    if not np.all((bit_array == 0) | (bit_array == 1)):
        raise ValueError("bits must contain only 0 and 1")

    return np.where(bit_array == 0, 1.0, -1.0)
