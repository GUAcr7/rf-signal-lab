import pytest
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'experiments'))
from p70_cold_prepare import archive_marker
from rfsig.board_session import WORK

def test_empty_file_does_not_confuse_console_success_marker_with_archive():
    assert archive_marker('\r\n__P46_f2ebc8ec__:0\r\n') is None

def test_valid_digest_with_console_framing():
    assert archive_marker('a'*64+'  '+WORK+'/e.gz\r\n\r\n__P46_f2ebc8ec__:0\r\n')=='a'*64

@pytest.mark.parametrize('text',['garbage\n__P46_f2ebc8ec__:0','a'*64+'  /tmp/other.gz',
    'a'*64+' '+WORK+'/e.gz\n'+'b'*64+' '+WORK+'/e.gz'])
def test_malformed_wrong_path_or_multiple_digest_is_not_an_existing_backup(text):
    with pytest.raises(ValueError):archive_marker(text)
