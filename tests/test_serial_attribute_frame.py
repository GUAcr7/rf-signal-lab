from pathlib import Path
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"experiments"))
from p26_restore_rx_profile import parse_attribute_frame


def test_wrap_and_echo_are_not_mistaken_for_attribute_values():
    trace="root@board:/long/path# echo __P26_VALUE__$(cat $a)__P26_END__\r\n" \
          "__P26_VALUE__0.000000 dB__P26_END__\r\nroot@board# echo __P22_RC__:$?\r\n__P22_RC__:0\r\n"
    assert parse_attribute_frame(trace)=="0.000000 dB"


@pytest.mark.parametrize("trace",["quency\n30720000\n", "__P26_VALUE__0__P26_END__\n__P26_VALUE__1__P26_END__\n"])
def test_missing_or_duplicate_frames_fail_closed(trace):
    with pytest.raises(RuntimeError):
        parse_attribute_frame(trace)
