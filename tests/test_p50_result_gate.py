import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'experiments'))
from p50_save_progress import machine_chain,physical_claim,passed_host_tests


def chain():
    cycle=dict(display_revision='p48',startup_origin='user_confirmed_power_cycle',power_cycles_observed=1,
        reboots_issued=0,minimum_running_seconds_requested=660,native_summary={'elapsed_software_s':700},expected_boot='new')
    clock=dict(status='passed_user_power_cycle_gated_clock_driver_register_consistency',trial_sha256='c',boot_id='new')
    policy=dict(status='passed_user_power_cycle_over_600s_no_X_console_blank_disabled_backlight_enabled',
        inputs={k:{'sha256':v} for k,v in [('cycle','c'),('review','r'),('cold_clock','k')]})
    enable=dict(status='passed_persistent_profile_rearmed_after_two_archived_warm_boots',true_power_cycle_verified=True,
        persistent_autostart_enabled=True,display_revision='p48',inputs={'current_cycle':{'sha256':'c'},'current_units':{'sha256':'u'}})
    state=dict(status='read_only_persistent_profile_state_collected',boot_id='new',enable_report_sha256='e',taint='0',
        RX_buffer='0',RX_scans=['0']*4,native_process_observed=False,persistent_wrapper_selected=True,
        pending_present=False,disabled_present=False,serial_closed=True)
    watch=dict(status='passed_cold_P48_progress_over_660s_RX_left_running',expected_boot='new',elapsed_software_s=700)
    return [cycle,clock,policy,enable,state,watch,'c','r','k','u','e']


def test_complete_machine_chain_is_separate_from_human_claim():
    assert machine_chain(*chain())
    assert physical_claim({},'new') is False


@pytest.mark.parametrize('change',['short','wrong-display','software-reboot','clock-boot','clock-hash',
    'policy','cold-claim','units','RX-active','pending','serial-open','watch-short','watch-boot'])
def test_incomplete_or_cross_boot_result_cannot_be_saved_as_verified(change):
    args=chain();c,k,p,e,s,w=args[:6]
    if change=='short':c['native_summary']['elapsed_software_s']=600
    elif change=='wrong-display':c['display_revision']='p42'
    elif change=='software-reboot':c['reboots_issued']=1
    elif change=='clock-boot':k['boot_id']='old'
    elif change=='clock-hash':k['trial_sha256']='other'
    elif change=='policy':p['status']='failed'
    elif change=='cold-claim':e['true_power_cycle_verified']=False
    elif change=='units':e['inputs']['current_units']['sha256']='other'
    elif change=='RX-active':s['RX_buffer']='1'
    elif change=='pending':s['pending_present']=True
    elif change=='serial-open':s['serial_closed']=False
    elif change=='watch-short':w['elapsed_software_s']=600
    elif change=='watch-boot':w['expected_boot']='old'
    with pytest.raises(ValueError):machine_chain(*args)


@pytest.mark.parametrize('change',[None,'boot','time','visibility','updates'])
def test_physical_confirmation_requires_same_boot_late_human_observation(change):
    h=dict(expected_boot='new',elapsed_software_s_at_question=660,
        physical_visibility_after_600s_confirmed=True,physical_updates_after_600s_confirmed=True)
    if change=='boot':h['expected_boot']='old'
    if change=='time':h['elapsed_software_s_at_question']=600
    if change=='visibility':h['physical_visibility_after_600s_confirmed']=False
    if change=='updates':h['physical_updates_after_600s_confirmed']=False
    assert physical_claim(h,'new') is (change is None)


@pytest.mark.parametrize('outcome',['','failure','error','skipped'])
def test_empty_junit_failure_elements_are_not_misread_as_success(tmp_path,outcome):
    xml=tmp_path/'test.xml'
    xml.write_text('<testsuite><testcase name="one">'+(f'<{outcome}/>' if outcome else '')+'</testcase></testsuite>')
    if outcome:
        with pytest.raises(ValueError):passed_host_tests(xml,minimum=1)
    else:assert passed_host_tests(xml,minimum=1)==1
