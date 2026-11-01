import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'experiments'))
from p70_cold_prepare import passive_startup_ready

@pytest.mark.parametrize('login',['Zynq-Tronlong login: ',
    'Zynq-Tronlong login: root (automatic login)\r\nroot@Zynq-Tronlong:~# ',
    'Zynq-Tronlong login: root (automatic login)\r\nudhcpc: discover...\r\n'])
def test_manual_or_automatic_login_after_new_kernel_and_ready(login):
    assert passive_startup_ready('Linux version 4.9\r\np43: PERSISTENT_MONITOR_READY\r\n'+login)

@pytest.mark.parametrize('text',['login: ','PERSISTENT_MONITOR_READY\nlogin: ',
    'Linux version 4.9\nlogin: ','Linux version 4.9\nPERSISTENT_MONITOR_READY\n'])
def test_incomplete_boot_is_not_ready(text):
    assert not passive_startup_ready(text)
