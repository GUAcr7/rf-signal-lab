import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'experiments'))
from p46_preflight import parse_names

def lines():return '\r\n'.join('__D__/sys/bus/iio/devices/iio:device'+str(i)+':'+n+'__E__' for i,n in enumerate(['ad9361-phy','cf-ad9361-lpc','cf-ad9361-dds-core-lpc']))

def test_echo_noise_between_device_frames_does_not_hide_real_device():
    text=lines().replace('\r\n','\r\necho __P32_abc__:$?\r\n')
    assert parse_names(text)['ad9361-phy'].endswith('device0')

def test_missing_or_duplicate_frames_rejected():
    for bad in [lines().split('\r\n',1)[1],lines()+'\r\n'+lines().split('\r\n')[0]]:
        with pytest.raises(ValueError):parse_names(bad)
