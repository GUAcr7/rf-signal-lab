import sys
from pathlib import Path
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'experiments'))
from p46_known_source import source_bytes_valid

def words(peak):
    x=np.zeros(262144,dtype='<i2');x[0]=peak;return x.tobytes()

def test_reviewed_component_peak256_in_packed_words_accepted():
    assert source_bytes_valid(words(4096))

@pytest.mark.parametrize('peak',[None,8192,4097],ids=['partial-file','peak512','padding-bits'])
def test_higher_peak_bad_layout_or_bad_padding_rejected(peak):
    raw=b'short' if peak is None else words(peak)
    with pytest.raises(ValueError):source_bytes_valid(raw)
