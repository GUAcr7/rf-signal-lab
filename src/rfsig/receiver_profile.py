"""Verified P70/P76 receiver selection; absent config preserves P58 baseline."""
import hashlib,json,re

def selected_profile(root,previous,provenance):
    config=root/'configs/receiver-profile.json'
    if not config.exists():return previous,provenance
    selection=json.loads(config.read_text(encoding='utf-8'))
    selection_sha=hashlib.sha256(config.read_bytes()).hexdigest()
    return _verify_selection(root,previous,provenance,selection,selection_sha)


def _verify_selection(root,previous,provenance,selection,selection_sha):
    def read(path):return json.loads(path.read_text(encoding='utf-8'))
    def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
    if selection.get('schema')!='rfsig.selected_receiver_profile.v1':raise ValueError('Receiver selection schema differs')
    path=selection.get('report','')
    if re.fullmatch(r'results/p76-boot-\d{8}T\d{6}Z/report\.json',path):
        return _verify_p76(root,previous,provenance,selection,selection_sha)
    if not re.fullmatch(r'results/p70-boot-\d{8}T\d{6}Z/report\.json',path):raise ValueError('Receiver profile path differs')
    path=root/path
    if sha(path)!=selection.get('report_sha256'):raise ValueError('Selected receiver report changed')
    profile=read(path)
    if (profile.get('schema')!='rfsig.receiver_profile.p70.v1'
        or profile.get('status')!='passed_P70_warm_boot_autonomous_ROI_display'
        or profile.get('reboots_issued')!=1 or profile.get('monitor_started_by_board_init') is not True
        or profile.get('true_power_cycle_verified') is not False
        or profile.get('previous_profile_report_sha256')!=provenance['accepted_boot_report_sha256']
        or profile.get('previous_wrapper_sha256')!=previous['installed_files_sha256']['boot']):
        raise ValueError('Unverified receiver profile or fallback identity')
    if not re.fullmatch(r'/etc/p43-\d{8}T\d{6}Z',profile.get('installed_directory','')):raise ValueError('Receiver install directory')
    files=profile.get('installed_files_sha256',{})
    if set(files)!={'original','monitor','control','run','bringup','boot','previous-boot'}:raise ValueError('Receiver snapshot membership differs')
    for name,wanted in files.items():
        if not re.fullmatch(r'[0-9a-f]{64}',wanted) or sha(path.parent/'files'/name)!=wanted:raise ValueError('Receiver snapshot changed: '+name)
    if files['monitor']!=profile.get('binary_sha256') or files['previous-boot']!=profile['previous_wrapper_sha256']:
        raise ValueError('Receiver app/fallback snapshot differs')
    review_name=profile.get('accepted_review','')
    if not re.fullmatch(r'results/p69-board-review-\d{8}T\d{6}Z/report\.json',review_name):raise ValueError('Receiver review path differs')
    review_path=root/review_name
    if sha(review_path)!=profile.get('accepted_review_sha256'):raise ValueError('Receiver review changed')
    review=read(review_path)
    if (review.get('status')!='passed_P69_native_ROI_RF_AI_pixels_and_invalidation'
        or review.get('binary_sha256')!=files['monitor']):raise ValueError('App is not the reviewed P69 binary')
    return profile,{**provenance,'prior_boot_report':provenance['accepted_boot_report'],
        'accepted_boot_report':str(path),'accepted_boot_report_sha256':sha(path),
        'selected_receiver_schema':profile['schema'],'receiver_selection_sha256':selection_sha}


def _verify_p76(root,previous,provenance,selection,selection_sha):
    def read(path):return json.loads(path.read_text(encoding='utf-8'))
    def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
    path=root/selection['report']
    if sha(path)!=selection.get('report_sha256'):raise ValueError('P76 profile report changed')
    profile=read(path)
    if (profile.get('schema')!='rfsig.receiver_profile.p76.v1'
        or profile.get('status')!='passed_P76_warm_boot_autonomous_phase_AI_display'
        or profile.get('reboots_issued')!=1 or profile.get('monitor_started_by_board_init') is not True
        or profile.get('true_power_cycle_verified') is not False
        or profile.get('release_scope')!='controlled_competition_demo'):
        raise ValueError('Unverified P76 startup or release scope')
    prior_path=path.parent/'previous-selection.json'
    if sha(prior_path)!=profile.get('previous_selection_sha256'):raise ValueError('Previous selection snapshot changed')
    prior_selection=read(prior_path)
    if (not re.fullmatch(r'results/p70-boot-\d{8}T\d{6}Z/report\.json',prior_selection.get('report',''))
        or prior_selection.get('report')!=profile.get('previous_profile_report')
        or prior_selection.get('report_sha256')!=profile.get('previous_profile_report_sha256')):
        raise ValueError('P76 previous profile must be the verified P70')
    prior,prior_source=_verify_selection(root,previous,provenance,prior_selection,sha(prior_path))
    if (profile.get('previous_wrapper_sha256')!=prior['installed_files_sha256']['boot']
        or not re.fullmatch(r'/etc/p43-\d{8}T\d{6}Z',profile.get('installed_directory',''))):
        raise ValueError('P76 fallback or installation identity differs')
    files=profile.get('installed_files_sha256',{})
    if set(files)!={'original','monitor','control','run','bringup','boot','previous-boot'}:
        raise ValueError('P76 snapshot membership differs')
    for name,wanted in files.items():
        if not re.fullmatch(r'[0-9a-f]{64}',wanted) or sha(path.parent/'files'/name)!=wanted:
            raise ValueError('P76 snapshot changed: '+name)
    if files['monitor']!=profile.get('binary_sha256') or files['previous-boot']!=profile['previous_wrapper_sha256']:
        raise ValueError('P76 app/fallback differs')
    review_name=profile.get('accepted_review','')
    if not re.fullmatch(r'results/p75-review-\d{8}T\d{6}Z/report\.json',review_name):raise ValueError('P76 review path')
    review_path=root/review_name
    if sha(review_path)!=profile.get('accepted_review_sha256'):raise ValueError('P76 RF review changed')
    review=read(review_path)
    gates=review.get('gates',[])
    if (review.get('status')!='passed_P75_prospective_RF_history_phase_replay_metrics_and_cleanup'
        or review.get('candidate_live_RAM_verified') is not True or not gates
        or not all(g.get('passed') is True for g in gates)):
        raise ValueError('P76 RF acceptance absent')
    trial_name=review.get('trial','')
    if not re.fullmatch(r'results/p59-p75-phase-candidate-\d{8}T\d{12}Z/report\.json',trial_name):
        raise ValueError('P76 RF trial path')
    trial_path=root/trial_name
    if sha(trial_path)!=review.get('trial_sha256'):raise ValueError('P76 RF trial changed')
    trial=read(trial_path)
    build_name=trial.get('build','')
    if not re.fullmatch(r'results/p75-build-\d{8}T\d{6}Z/report\.json',build_name):raise ValueError('P76 build path')
    build_path=root/build_name
    if sha(build_path)!=trial.get('build_sha256') or read(build_path).get('binary_sha256')!=files['monitor']:
        raise ValueError('P76 app is not the reviewed phase candidate')
    return profile,{**prior_source,'prior_boot_report':prior_source['accepted_boot_report'],
        'accepted_boot_report':str(path),'accepted_boot_report_sha256':sha(path),
        'selected_receiver_schema':profile['schema'],'receiver_selection_sha256':selection_sha}
