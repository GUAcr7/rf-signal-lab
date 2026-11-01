import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'experiments'))
from p43_capture_power_on import startup_ready

def test_auto_login_prompt_is_ready_without_uart_input():
    assert startup_ready('Linux version 4.9\np43: PERSISTENT_MONITOR_READY\nroot@Zynq-Tronlong:~# ')

def test_real_terminal_escape_before_root_prompt_does_not_hide_login():
    assert startup_ready('Linux version 4.9\np43: PERSISTENT_MONITOR_READY\n\x1b7\x1b[r\x1b[999;999H\x1b[6nroot@Zynq-Tronlong:~# ')

def test_login_prompt_also_accepted():
    assert startup_ready('U-Boot\np43: PERSISTENT_MONITOR_READY\nboard login: ')

def test_old_shell_or_incomplete_boot_cannot_be_ready():
    for text in ['root@Zynq-Tronlong:~# ','Linux version 4.9\nroot@board:~# ','p43: PERSISTENT_MONITOR_READY\nroot@board:~# ']:
        assert not startup_ready(text)
