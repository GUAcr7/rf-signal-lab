"""Explicit Gray-labelled, unit-constellation-power modulation references."""

import numpy as np
from numpy.typing import NDArray


def _groups(bits, size: int) -> NDArray[np.uint8]:
    values = np.asarray(bits)
    if values.ndim != 1 or values.size == 0 or values.size % size:
        raise ValueError(f"bits must be nonempty, one-dimensional and a multiple of {size}")
    if not np.all((values == 0) | (values == 1)):
        raise ValueError("bits must contain only 0 and 1")
    return values.astype(np.uint8).reshape(-1, size)


def map_qpsk(bits) -> NDArray[np.complex128]:
    """Each pair b0,b1 maps to ((1-2*b0)+j*(1-2*b1))/sqrt(2).

    00 -> (+,+), 01 -> (+,-), 11 -> (-,-), 10 -> (-,+).
    Adjacent constellation states differ by one bit (Gray labelling).
    """
    pairs = _groups(bits, 2).astype(np.float64)
    return ((1-2*pairs[:,0]) + 1j*(1-2*pairs[:,1])) / np.sqrt(2)


def map_qam16(bits) -> NDArray[np.complex128]:
    """b0,b1 choose I; b2,b3 choose Q: 00=-3,01=-1,11=+1,10=+3.

    Divide by sqrt(10) so the equiprobable 16-point constellation has
    average power 1. A finite random record need not have exactly power 1.
    """
    groups = _groups(bits, 4)
    levels = np.array([-3., -1., 3., 1.])
    i = levels[2*groups[:,0]+groups[:,1]]
    q = levels[2*groups[:,2]+groups[:,3]]
    return (i + 1j*q) / np.sqrt(10)
