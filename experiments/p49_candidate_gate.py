"""Pure host gates for explicit P48 app migration; no board access."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads(Path(p).read_text('utf-8'))
def path(p):
    p=Path(p);return p if p.is_absolute() else ROOT/p
def sha(p):return hashlib.sha256(path(p).read_bytes()).hexdigest()

def validate_candidate(suite_path,build_path,status_path,reuse_cycle=None,observation=None,observation_review=None):
    suite=read(suite_path);build=read(build_path);status=read(status_path)
    if (suite['status']!='passed_P48_finite_display_units_candidate_and_original_startup_rearmed'
        or not suite['candidate_checks_passed'] or not suite['startup_selection_rearmed'] or not suite['RX_idle']
        or not suite['serial_closed'] or suite['TX_operations'] or suite['PL_changes'] or suite['reboots_issued']):
        raise ValueError('accepted stopped P48 candidate required')
    if (path(suite['inputs']['build']['path']).resolve()!=Path(build_path).resolve()
        or suite['inputs']['build']['sha256']!=sha(build_path)
        or build.get('display_revision')!='p48' or build.get('runtime_engine')!='p42'
        or build['status']!='passed_native_mock_tests_and_ARM_build_not_board_test' or build['test_count']<32
        or not build['target_checks'] or not all(build['target_checks'].values()) or sha(build['binary'])!=build['binary_sha256']):
        raise ValueError('explicit tested P48 build differs')
    for name,digest in build['inputs_sha256'].items():
        if sha(name)!=digest:raise ValueError('build source changed')
    for child in suite['stages']:
        if child['exit_code']!=0 or sha(child['report'])!=child['report_sha256']:raise ValueError('candidate evidence changed')
    bound={path(c['report']).resolve() for c in suite['stages']}
    if any(path(suite[k]).resolve() not in bound for k in ('trial','review','units')):
        raise ValueError('candidate trial/review/units must be hash-bound stages')
    units=read(path(suite['units']))
    if (units['status']!='passed_P48_frequency_units_and_exact_framebuffer_glyphs' or not units['checks'] or not all(units['checks'].values())
        or units['trial_sha256']!=sha(suite['trial']) or units['review_sha256']!=sha(suite['review'])):
        raise ValueError('display-unit evidence differs')
    boot=suite['expected_boot']
    if bool(observation)!=bool(observation_review) or (reuse_cycle and observation):
        raise ValueError('one complete observation/review pair or preceding cycle required')
    if observation:
        from p43_finish_enable import reviewed
        observed,_=reviewed(Path(observation),Path(observation_review),require_clock=False)
        enable_path=path(status['enable_report']);enable=read(enable_path)
        if (sha(enable_path)!=status['enable_report_sha256']
            or enable['status']!='passed_persistent_profile_rearmed_after_two_archived_warm_boots'
            or observed.get('startup_origin')!='existing_new_boot_power_cycle_not_verified'
            or observed['reboots_issued']!=0 or observed['power_cycles_observed']!=0
            or not observed['fresh_empty_boot_verified']
            or observed['installed_directory']!=enable['installed_directory']
            or observed['installed_files_sha256']!=enable['installed_files_sha256']
            or path(observed['inputs']['enable_report']['path']).resolve()!=enable_path.resolve()):
            raise ValueError('observed current boot must retain the exact accepted original profile')
        for item in observed['inputs'].values():
            if sha(item['path'])!=item['sha256']:raise ValueError('observation input changed')
        boot=observed['expected_boot']
    if reuse_cycle:
        previous=read(reuse_cycle)
        if (previous.get('status')!='passed_long_running_RX_LCD_progress_and_independent_idle'
            or previous.get('display_revision')!='p48' or previous['binary_sha256']!=build['binary_sha256']
            or not previous['serial_closed'] or not previous['independent_final_idle_verified']
            or not previous['startup_paused_for_archiving']):raise ValueError('preceding P48 cycle required')
        boot=previous['expected_boot']
    if (status['status']!='read_only_persistent_profile_state_collected' or status['boot_id']!=boot or status['taint']!='0'
        or status['RX_buffer']!='0' or status['RX_scans']!=['0']*4 or status['native_process_observed']
        or status['pending_present'] or status['disabled_present'] or not status['serial_closed']
        or status['mode']!='rf' or status['persistent_wrapper_selected']):
        raise ValueError('matching current idle boot required; refresh identity and candidate if boot changed')
    return suite,boot
