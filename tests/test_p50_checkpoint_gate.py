import json,sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'experiments'))
import p43_prepare_power_cycle as prepare
from p50_watch_startup import check_policy


@pytest.fixture
def saved(tmp_path,monkeypatch):
    monkeypatch.setattr(prepare,'ROOT',tmp_path)
    enable=tmp_path/'enable.json'
    enable.write_text(json.dumps(dict(display_revision='p48',persistent_autostart_enabled=True,serial_closed=True)))
    checkpoint=dict(status='passed_P49_checkpoint_ZIP_CRC_and_all_member_SHA',
        reports={'enable':dict(path='enable.json',sha256=prepare.sha(enable))})
    return enable,checkpoint


def test_exact_saved_p48_checkpoint_can_prepare_new_cold_test(saved):
    assert prepare.checkpoint_phase(*saved)=='p50'


def test_completed_p50_checkpoint_can_prepare_a_later_repeat(saved):
    enable,checkpoint=saved;checkpoint['status']='passed_P50_checkpoint_ZIP_CRC_and_all_member_SHA'
    assert prepare.checkpoint_phase(enable,checkpoint)=='p50'


@pytest.mark.parametrize('change',['path','hash','phase','wrong-display','not-enabled','serial-open'])
def test_stale_or_different_checkpoint_is_rejected(saved,change):
    enable,checkpoint=saved
    if change=='path':checkpoint['reports']['enable']['path']='other.json'
    elif change=='hash':checkpoint['reports']['enable']['sha256']='bad'
    elif change=='phase':checkpoint['status']='passed_unknown'
    else:
        value=json.loads(enable.read_text())
        value[{'wrong-display':'display_revision','not-enabled':'persistent_autostart_enabled','serial-open':'serial_closed'}[change]]='p42' if change=='wrong-display' else False
        enable.write_text(json.dumps(value));checkpoint['reports']['enable']['sha256']=prepare.sha(enable)
    with pytest.raises(ValueError):prepare.checkpoint_phase(enable,checkpoint)


@pytest.mark.parametrize('change',[None,'blanking','marker','backlight','desktop'])
def test_after_threshold_policy_rejects_blanking_or_unlit_screen(change):
    policy=dict(consoleblank='0',marker='RF_PANEL_NO_X_DPMS',
        PWM=' pwm-2 (backlight): requested enabled period: 100000 ns duty: 50000 ns',processes=' 1 0 /sbin/init')
    if change=='blanking':policy['consoleblank']='600'
    if change=='marker':policy['marker']='missing'
    if change=='backlight':policy['PWM']=policy['PWM'].replace(' enabled',' disabled')
    if change=='desktop':policy['processes']+='\n 55 1 /usr/bin/Xorg :0'
    if change:
        with pytest.raises(ValueError):check_policy(policy)
    else:assert check_policy(policy)==policy
