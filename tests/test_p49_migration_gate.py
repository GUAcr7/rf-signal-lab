"""Synthetic fixtures test migration safety; these are not board evidence."""
import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'experiments'))
import p49_candidate_gate as gate
from p48_verify_units import validated_sample_rate
from p36_full_rx_run import RF_EXPECTED
from p43_finish_enable import checked_units


def put(p, value):
    p.write_text(json.dumps(value), encoding='utf-8')
    return p


@pytest.fixture
def evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, 'ROOT', tmp_path)
    (tmp_path / 'source.c').write_bytes(b'source')
    (tmp_path / 'monitor').write_bytes(b'ELF')
    build=dict(display_revision='p48', runtime_engine='p42',
        status='passed_native_mock_tests_and_ARM_build_not_board_test', test_count=32,
        target_checks={'ABI':True}, binary='monitor', binary_sha256=gate.sha('monitor'),
        inputs_sha256={'source.c':gate.sha('source.c')})
    put(tmp_path/'build.json',build)
    put(tmp_path/'trial.json',{'synthetic':True})
    put(tmp_path/'review.json',{'synthetic':True})
    put(tmp_path/'units.json',dict(status='passed_P48_frequency_units_and_exact_framebuffer_glyphs',
        checks={'pixels':True},trial_sha256=gate.sha('trial.json'),review_sha256=gate.sha('review.json')))
    suite=dict(status='passed_P48_finite_display_units_candidate_and_original_startup_rearmed',
        candidate_checks_passed=True,startup_selection_rearmed=True,RX_idle=True,serial_closed=True,
        TX_operations=False,PL_changes=False,reboots_issued=0,expected_boot='old',
        inputs={'build':{'path':'build.json','sha256':gate.sha('build.json')}},
        trial='trial.json',review='review.json',units='units.json',
        stages=[dict(report=n,exit_code=0,report_sha256=gate.sha(n)) for n in ('trial.json','review.json','units.json')])
    put(tmp_path/'suite.json',suite)
    status=dict(status='read_only_persistent_profile_state_collected',boot_id='old',taint='0',
        RX_buffer='0',RX_scans=['0']*4,native_process_observed=False,pending_present=False,
        disabled_present=False,serial_closed=True,mode='rf',persistent_wrapper_selected=False)
    put(tmp_path/'state.json',status)
    return tmp_path,suite,build,status


def validate(evidence, **kw):
    root=evidence[0]
    return gate.validate_candidate(root/'suite.json',root/'build.json',root/'state.json',**kw)


def test_accepted_matching_stopped_candidate(evidence):
    assert validate(evidence)[1]=='old'


@pytest.mark.parametrize('field,value',[
    ('boot_id','another-boot'),('taint','512'),('RX_buffer','1'),('RX_scans',['1','1','0','0']),
    ('native_process_observed',True),('pending_present',True),('disabled_present',True),
    ('serial_closed',False),('mode','lcd'),('persistent_wrapper_selected',True),('status','failed_or_unconfirmed')])
def test_live_or_stale_or_unprepared_state_rejected(evidence,field,value):
    root,_,_,state=evidence;state[field]=value;put(root/'state.json',state)
    with pytest.raises(ValueError,match='current idle boot'):validate(evidence)


@pytest.mark.parametrize('field,value',[
    ('candidate_checks_passed',False),('startup_selection_rearmed',False),('RX_idle',False),
    ('TX_operations',True),('PL_changes',True),('reboots_issued',1)])
def test_incomplete_candidate_rejected(evidence,field,value):
    root,suite,_,_=evidence;suite[field]=value;put(root/'suite.json',suite)
    with pytest.raises(ValueError,match='accepted stopped'):validate(evidence)


@pytest.mark.parametrize('file',['source.c','monitor','trial.json','review.json','units.json','build.json'])
def test_altered_source_binary_or_evidence_rejected(evidence,file):
    root=evidence[0]
    with (root/file).open('ab') as f:f.write(b' ')
    with pytest.raises(ValueError):validate(evidence)


def test_units_cannot_be_swapped_for_an_unbound_report(evidence):
    root,suite,_,_=evidence
    (root/'other-units.json').write_bytes((root/'units.json').read_bytes())
    suite['units']='other-units.json';put(root/'suite.json',suite)
    with pytest.raises(ValueError,match='hash-bound'):validate(evidence)


def test_second_cycle_uses_new_boot_without_rewriting_original_evidence(evidence):
    root,_,build,state=evidence
    previous=dict(status='passed_long_running_RX_LCD_progress_and_independent_idle',display_revision='p48',
        binary_sha256=build['binary_sha256'],serial_closed=True,independent_final_idle_verified=True,
        startup_paused_for_archiving=True,expected_boot='new')
    prior=put(root/'previous.json',previous)
    state['boot_id']='new';put(root/'state.json',state)
    assert validate(evidence,reuse_cycle=prior)[1]=='new'
    previous['status']='failed';put(prior,previous)
    with pytest.raises(ValueError,match='preceding P48'):validate(evidence,reuse_cycle=prior)


def test_incomplete_boot_bridge_rejected(evidence):
    with pytest.raises(ValueError,match='complete observation'):validate(evidence,observation='missing')


@pytest.mark.parametrize('kind',['finite','autonomous'])
def test_units_use_verified_rf_attributes_for_each_record_type(kind):
    key='before' if kind=='finite' else 'armed_state'
    trial={key:{'attributes':dict(RF_EXPECTED)},'after':{'attributes':dict(RF_EXPECTED)}}
    assert validated_sample_rate(trial)==30720000
    trial['after']['attributes']['in_voltage_sampling_frequency']='1000000'
    with pytest.raises(ValueError,match='pre/post RF'):validated_sample_rate(trial)


def test_units_do_not_guess_rate_from_metrics_or_constants():
    with pytest.raises(ValueError,match='pre/post RF'):validated_sample_rate({'sample_rate_hz':30720000})


def test_migrated_profile_requires_exact_unit_review_before_enable(tmp_path):
    trial=put(tmp_path/'trial.json',{'synthetic':True})
    review=put(tmp_path/'review.json',{'synthetic':True})
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    value=dict(status='passed_P48_frequency_units_and_exact_framebuffer_glyphs',trial=str(trial),review=str(review),
        trial_sha256=digest(trial),review_sha256=digest(review),
        checks={k:True for k in ('peak_offset_pixels_exact','sample_rate_pixels_exact','FFT_spacing_pixels_exact')})
    units=put(tmp_path/'units.json',value)
    assert checked_units(trial,review,units)==value
    value['checks']['sample_rate_pixels_exact']=False;put(units,value)
    with pytest.raises(ValueError,match='unit and glyph'):checked_units(trial,review,units)
    value['checks']['sample_rate_pixels_exact']=True;put(units,value)
    trial.write_bytes(b'changed')
    with pytest.raises(ValueError,match='unit and glyph'):checked_units(trial,review,units)


@pytest.mark.parametrize('change',[None,'origin','profile','reboot','enable-hash','input-hash'])
def test_observed_boot_bridge_preserves_provenance(evidence,monkeypatch,change):
    import p43_finish_enable
    root,_,_,state=evidence
    enable=dict(status='passed_persistent_profile_rearmed_after_two_archived_warm_boots',
        installed_directory='/etc/original',installed_files_sha256={'monitor':'exact'})
    ep=put(root/'enable.json',enable)
    state.update(boot_id='observed',enable_report=str(ep),enable_report_sha256=gate.sha(ep));put(root/'state.json',state)
    observed=dict(expected_boot='observed',startup_origin='existing_new_boot_power_cycle_not_verified',
        reboots_issued=0,power_cycles_observed=0,fresh_empty_boot_verified=True,
        installed_directory=enable['installed_directory'],installed_files_sha256=enable['installed_files_sha256'],
        inputs={'enable_report':{'path':str(ep),'sha256':gate.sha(ep)}})
    if change=='origin':observed['startup_origin']='user_confirmed_power_cycle'
    if change=='profile':observed['installed_directory']='/etc/different'
    if change=='reboot':observed['reboots_issued']=1
    if change=='enable-hash':state['enable_report_sha256']='bad';put(root/'state.json',state)
    if change=='input-hash':observed['inputs']['enable_report']['sha256']='bad'
    # The archive review has its own tests; isolate bridge-specific policy here.
    monkeypatch.setattr(p43_finish_enable,'reviewed',lambda *a,**k:(observed,{}))
    if change:
        with pytest.raises(ValueError):validate(evidence,observation=root/'observed.json',observation_review=root/'review.json')
    else:
        assert validate(evidence,observation=root/'observed.json',observation_review=root/'review.json')[1]=='observed'
