import json
import pytest
from test_receiver_profile_p70 import tree,digest
from rfsig.receiver_profile import selected_profile


@pytest.fixture
def candidate(tree):
    root,old,provenance,p70,select=tree;select()
    def write(name,obj):
        p=root/name;p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(json.dumps(obj),encoding='utf-8');return p
    name='results/p76-boot-20261026T140000Z/report.json'
    folder=root/'results/p76-boot-20261026T140000Z/files';folder.mkdir(parents=True)
    files={}
    for key in ('original','monitor','control','run','bringup','boot','previous-boot'):
        raw=b'boot' if key=='previous-boot' else ('p76-'+key).encode()
        (folder/key).write_bytes(raw);files[key]=digest(raw)
    prior=(root/'configs/receiver-profile.json').read_bytes()
    (folder.parent/'previous-selection.json').write_bytes(prior)
    previous=json.loads(prior)
    build=write('results/p75-build-20261026T130000Z/report.json',dict(binary_sha256=files['monitor']))
    trial=write('results/p59-p75-phase-candidate-20261026T130100000000Z/report.json',
                dict(build=build.relative_to(root).as_posix(),build_sha256=digest(build.read_bytes())))
    review=write('results/p75-review-20261026T133000Z/report.json',
        dict(status='passed_P75_prospective_RF_history_phase_replay_metrics_and_cleanup',
             candidate_live_RAM_verified=True,gates=[dict(passed=True)],
             trial=trial.relative_to(root).as_posix(),trial_sha256=digest(trial.read_bytes())))
    profile=dict(schema='rfsig.receiver_profile.p76.v1',status='passed_P76_warm_boot_autonomous_phase_AI_display',
        reboots_issued=1,monitor_started_by_board_init=True,true_power_cycle_verified=False,
        release_scope='controlled_competition_demo',previous_selection_sha256=digest(prior),
        previous_profile_report=previous['report'],previous_profile_report_sha256=previous['report_sha256'],
        previous_wrapper_sha256=p70['installed_files_sha256']['boot'],
        installed_directory='/etc/p43-20261026T140000Z',installed_files_sha256=files,binary_sha256=files['monitor'],
        accepted_review=review.relative_to(root).as_posix(),accepted_review_sha256=digest(review.read_bytes()))
    def commit():
        report=write(name,profile)
        write('configs/receiver-profile.json',dict(schema='rfsig.selected_receiver_profile.v1',report=name,report_sha256=digest(report.read_bytes())))
    return root,old,provenance,profile,commit,build,trial,review


def test_verified_p76_preserves_verified_p70_chain(candidate):
    root,old,provenance,profile,commit,*_=candidate;commit()
    result,source=selected_profile(root,old,provenance)
    assert result==profile and source['selected_receiver_schema']=='rfsig.receiver_profile.p76.v1'
    assert 'p70-boot-' in source['prior_boot_report']


@pytest.mark.parametrize('key,value',[
    ('status','installing'),('reboots_issued',0),('monitor_started_by_board_init',False),
    ('true_power_cycle_verified',True),('release_scope','general_unknown_signals'),
    ('previous_selection_sha256','0'*64),('previous_profile_report','../../wrong'),
    ('previous_wrapper_sha256','0'*64),('installed_directory','/etc/wrong'),('binary_sha256','0'*64),
])
def test_p76_unverified_states_fail_closed(candidate,key,value):
    root,old,provenance,p,commit,*_=candidate;p[key]=value;commit()
    with pytest.raises(ValueError):selected_profile(root,old,provenance)


@pytest.mark.parametrize('target',['previous-selection','monitor','previous-boot','build','trial','review','p70'])
def test_p76_tampering_fails_closed(candidate,target):
    root,old,provenance,p,commit,build,trial,review=candidate;commit()
    if target in ('monitor','previous-boot'):path=root/'results/p76-boot-20261026T140000Z/files'/target
    elif target=='previous-selection':path=root/'results/p76-boot-20261026T140000Z/previous-selection.json'
    elif target=='p70':path=root/'results/p70-boot-20261026T120000Z/report.json'
    else:path={'build':build,'trial':trial,'review':review}[target]
    path.write_bytes(b'changed')
    with pytest.raises((ValueError,json.JSONDecodeError)):selected_profile(root,old,provenance)


def test_failed_rf_gate_cannot_be_selected_even_with_resealed_review(candidate):
    root,old,provenance,p,commit,_,_,review=candidate
    data=json.loads(review.read_text());data['gates']=[dict(passed=False)]
    review.write_text(json.dumps(data));p['accepted_review_sha256']=digest(review.read_bytes());commit()
    with pytest.raises(ValueError):selected_profile(root,old,provenance)
