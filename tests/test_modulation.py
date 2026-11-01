import numpy as np
import pytest
from itertools import product

from rfsig.modulation import map_qpsk, map_qam16


def test_qpsk_hand_calculated_four_states():
    actual = map_qpsk([0,0, 0,1, 1,1, 1,0])
    expected = np.array([1+1j,1-1j,-1-1j,-1+1j]) / np.sqrt(2)
    np.testing.assert_allclose(actual,expected,rtol=0,atol=1e-14)
    np.testing.assert_allclose(np.abs(actual)**2,1,rtol=0,atol=1e-14)
    assert actual.dtype == np.complex128
    assert len(np.unique(actual)) == 4


@pytest.mark.parametrize('bits',[[],[0],[0,1,0],[[0,1]],[0,2],[np.nan,0]])
def test_qpsk_rejects_incomplete_or_invalid_pairs(bits):
    with pytest.raises(ValueError):
        map_qpsk(bits)


def test_qam16_all_states_match_explicit_gray_axis_table():
    bits = np.array(list(product([0,1],repeat=4)),dtype=np.uint8)
    # Independent table, indexed by the actual bit-pair strings.
    levels = {(0,0):-3,(0,1):-1,(1,1):1,(1,0):3}
    expected = np.array([levels[tuple(row[:2])] + 1j*levels[tuple(row[2:])]
                         for row in bits]) / np.sqrt(10)
    actual = map_qam16(bits.ravel())
    np.testing.assert_allclose(actual,expected,rtol=0,atol=1e-14)
    assert len(np.unique(actual)) == 16
    np.testing.assert_allclose(np.mean(np.abs(actual)**2),1,rtol=0,atol=1e-14)
    np.testing.assert_allclose([np.min(np.abs(actual)**2),np.max(np.abs(actual)**2)],
                               [.2,1.8],rtol=0,atol=1e-14)


@pytest.mark.parametrize('bits',[[],[0,1],[0,1,0],[[0,1,0,1]],[0,0,0,2],[0,0,0,np.nan]])
def test_qam16_rejects_incomplete_or_invalid_groups(bits):
    with pytest.raises(ValueError):
        map_qam16(bits)
