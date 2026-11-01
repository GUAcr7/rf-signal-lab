"""Exercise the real P57 shells with P43's isolated mock filesystem."""
import subprocess
import pytest
import test_p43_boot_shell as legacy
import p57_boot_templates as candidate
from p36_build_rx_full import posix

@pytest.fixture(autouse=True)
def use_candidate(monkeypatch):
    monkeypatch.setattr(legacy.templates,'render',candidate.render)

def test_ready_and_owned_stop(tmp_path,monkeypatch):
    legacy.test_persistent_shell_keeps_guard_clears_latch_and_owned_stop(tmp_path,monkeypatch)

@pytest.mark.parametrize('kind',['old_boot','wrong_original','wrong_runtime','wrong_bit','existing_overlay','existing_RF','repeat_boot','not_RAM'])
def test_hardware_preconditions(tmp_path,monkeypatch,kind):
    legacy.test_failed_preconditions_never_program_PL(tmp_path,monkeypatch,kind)

@pytest.mark.parametrize('kind',['disabled','pending'])
def test_latched_fallback(tmp_path,monkeypatch,kind):
    legacy.test_new_boot_disabled_or_stale_initialization_selects_factory_once(tmp_path,monkeypatch,kind)

@pytest.mark.parametrize('kind',['probe_failure','no_progress'])
def test_no_hot_retry(tmp_path,monkeypatch,kind):
    legacy.test_incomplete_boot_preserves_pending_without_hot_retry(tmp_path,monkeypatch,kind)

def test_calibration_is_boot_bound_atomic_owned_and_has_no_class_label(tmp_path,monkeypatch):
    base,d,firmware,wrapper,result=legacy.scenario(tmp_path,monkeypatch,'pass')
    assert result.returncode==0,result.stdout+result.stderr
    control=base/(d+'/control').lstrip('/');work=base/'run/p42-000043'
    def invoke(*args):return subprocess.run(['wsl.exe','--exec','sh',posix(control),*args],capture_output=True,timeout=15)
    try:
        for token in ('BPSK','0'*31,'0'*31+';','0'*33):
            assert invoke('calibrate',token).returncode!=0
            assert not (work/'control').exists()
        pid=work/'pid';owned=pid.read_bytes();pid.write_text('1\n')
        assert invoke('calibrate','0'*32).returncode!=0
        assert not (work/'control').exists();pid.write_bytes(owned)
        result=invoke('calibrate','a'*32);assert result.returncode==0,result.stdout+result.stderr
        assert (work/'control').read_text().split()==['P56CAL1',legacy.FRESH,candidate.MODEL_SHA,'a'*32]
        assert not (work/'control.next').exists()
        marker=base/'run/p43-init-boot';marker.write_text(legacy.ARMED)
        before=(work/'control').read_bytes();assert invoke('calibrate','b'*32).returncode!=0
        assert (work/'control').read_bytes()==before;marker.write_text(legacy.FRESH)
    finally:
        assert invoke('stop').returncode==0
    assert invoke('calibrate','c'*32).returncode!=0

def test_launcher_is_bounded_and_never_transmits():
    files=candidate.render('/etc/p43-20261024T100000Z',legacy.ARMED,'0'*64,
        '/lib/firmware/p35-ttl-20261021T090121Z.bin','1'*64,'/lib/firmware/p35-merged-20261021T090121Z.dtbo','2'*64)
    launch=files['run'].decode()
    assert '900000 500' in launch and 'timeout -k 22 930 ' in launch
    assert 'P56_CONTROL_FILE' in launch and 'P56_SHOT_FILE' in launch
    assert '--run' not in launch and 'RF_LINK_REVIEWED' not in launch
