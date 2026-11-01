import hashlib,json
from pathlib import Path
import pytest
from rfsig.receiver_profile import selected_profile

def digest(data):return hashlib.sha256(data).hexdigest()

@pytest.fixture
def tree(tmp_path):
    def write(path,value):
        path=tmp_path/path;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(value),encoding='utf-8');return path
    previous=dict(installed_files_sha256=dict(boot=digest(b'previous-boot')))
    provenance=dict(accepted_boot_report='old/report.json',accepted_boot_report_sha256='a'*64)
    folder=tmp_path/'results/p70-boot-20261026T120000Z/files';folder.mkdir(parents=True)
    files={}
    for name in ('original','monitor','control','run','bringup','boot','previous-boot'):
        (folder/name).write_bytes(name.encode());files[name]=digest(name.encode())
    review_name='results/p69-board-review-20261026T110000Z/report.json'
    review=write(review_name,dict(status='passed_P69_native_ROI_RF_AI_pixels_and_invalidation',binary_sha256=files['monitor']))
    name='results/p70-boot-20261026T120000Z/report.json'
    profile=dict(schema='rfsig.receiver_profile.p70.v1',status='passed_P70_warm_boot_autonomous_ROI_display',
        reboots_issued=1,monitor_started_by_board_init=True,true_power_cycle_verified=False,
        previous_profile_report_sha256='a'*64,previous_wrapper_sha256=previous['installed_files_sha256']['boot'],
        installed_directory='/etc/p43-20261026T120000Z',installed_files_sha256=files,
        binary_sha256=files['monitor'],accepted_review=review_name,accepted_review_sha256=digest(review.read_bytes()))
    def select():
        report=write(name,profile)
        write('configs/receiver-profile.json',dict(schema='rfsig.selected_receiver_profile.v1',report=name,report_sha256=digest(report.read_bytes())))
    return tmp_path,previous,provenance,profile,select

def test_no_selection_keeps_original_profile(tree):
    root,old,provenance,_,_=tree
    assert selected_profile(root,old,provenance)==(old,provenance)

def test_verified_selection_retains_old_provenance(tree):
    root,old,provenance,profile,select=tree;select()
    actual,source=selected_profile(root,old,provenance)
    assert actual==profile and source['prior_boot_report']=='old/report.json'
    assert Path(source['accepted_boot_report']).as_posix().endswith('p70-boot-20261026T120000Z/report.json')

@pytest.mark.parametrize('key,value',[
    ('status','installing'),('reboots_issued',0),('monitor_started_by_board_init',False),
    ('true_power_cycle_verified',True),('previous_profile_report_sha256','b'*64),
    ('previous_wrapper_sha256','b'*64),('installed_directory','/etc/elsewhere'),
    ('binary_sha256','b'*64),('accepted_review','../../outside.json'),
])
def test_unverified_profiles_are_rejected_without_fallback(tree,key,value):
    root,old,provenance,profile,select=tree;profile[key]=value;select()
    with pytest.raises(ValueError):selected_profile(root,old,provenance)

@pytest.mark.parametrize('target',['monitor','previous-boot','review','report','config'])
def test_tampered_artifacts_fail_closed(tree,target):
    root,old,provenance,_,select=tree;select()
    if target in ('monitor','previous-boot'):(root/'results/p70-boot-20261026T120000Z/files'/target).write_bytes(b'changed')
    elif target=='review':(root/'results/p69-board-review-20261026T110000Z/report.json').write_text('{}')
    elif target=='report':(root/'results/p70-boot-20261026T120000Z/report.json').write_text('{}')
    else:(root/'configs/receiver-profile.json').write_text('{"schema":"wrong"}')
    with pytest.raises(ValueError):selected_profile(root,old,provenance)
