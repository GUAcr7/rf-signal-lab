"""Save a scoped P31 status and checksum checkpoint, including ignored evidence."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = {
    'timing_sources':'p31-timing-sources-20261019T140648Z',
    'factory_contract':'p31-board-contract-20261019T135528Z',
    'dtc_tools':'p31-dtc-tools-20261019T135813Z',
    'overlay':'p31-overlay-20261019T141549Z',
    'contract':'p31-contract-verification-20261019T143056Z',
    'fifo':'p31-fifo-test-20261019T140637Z',
    'arbiter':'p31-arbiter-test-20261019T141159Z',
    'failed_hot_unload':'p31-rf-driver-test-20261019T141834Z',
    'console_observation':'p31-oops-observation-20261019T142127Z',
    'failed_sysrq':'p31-sysrq-recovery-20261019T142254Z',
    'repowered':'p31-repowered-20261019T142539Z',
    'initial_RX_restore':'p26-rx-profile-restore-20261019T143009Z',
    'initial_sparse_smoke':'p27-smoke-20261019T143227Z',
    'initial_sparse_bytes':'p30-smoke-archive-20261019T143355Z',
    'initial_end_state':'p31-end-state-20261019T143602Z',
    'boot_guard_tests':'p31-boot-guard-20261019T142948Z',
    'boot_guard_deploy':'p31-boot-guard-deploy-20261019T143146Z',
    'guard_full_boot':'p31-guard-boot-20261019T144337Z',
    'RX_profile_restore':'p26-rx-profile-restore-20261019T144504Z',
    'sparse_smoke':'p27-smoke-20261019T144510Z',
    'rejected_whole_transfer':'p30-smoke-archive-20261019T144633Z',
    'sparse_bytes':'p31-sparse-archive-20261019T145054Z',
    'vendor_kernel':'p31-vendor-kernel-20261019T143355Z',
    'kernel_image':'p31-kernel-image-20261019T144415Z',
    'fault_instructions':'p31-remove-fault-20261019T144938Z',
    'end_state':'p31-end-state-20261019T145151Z',
}
RX_BOOT = 'ebce10b9-e464-4b4c-b586-d4fd8d116e06'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def logical_verilog(text):
    text = re.sub(r'/\*.*?\*/|//[^\n]*', '', text, flags=re.S)
    return re.sub(r'\s+', '', text)


def main():
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out = ROOT/'results'/('p31-checkpoint-'+stamp)
    out.mkdir(exist_ok=False)
    report = dict(status='checking', checks=[], files=[], board_operations=False,
        scope='Evidence and selected source checkpoint; not an independently rebuildable FPGA/toolchain delivery',
        historical_full_python_regression=864, full_regression_rerun=False)

    def save():
        (out/'report.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')

    def check(name, passed):
        report['checks'].append(dict(check=name, passed=bool(passed)))
        if not passed:
            save()
            raise RuntimeError(name)

    save()
    data = {key:json.loads((ROOT/'results'/folder/'report.json').read_text('utf-8')) for key,folder in EVIDENCE.items()}
    check('native overlay 240 checks', data['overlay']['checks_count']==240 and all(c['passed'] for c in data['overlay']['checks']))
    check('89 original AD9361 properties preserved', data['overlay']['protected_RF_properties']==89)
    check('independent BD contract and negative fixtures', data['contract']['status']=='passed' and
          len(data['contract']['checks'])==30 and all(n['detected'] for n in data['contract']['negative_fixtures']))
    check('independent contract is for latest candidate', Path(data['contract']['overlay_report'])==ROOT/'results'/EVIDENCE['overlay']/'report.json')
    fifo = [line for line in data['fifo']['markers'] if 'CASE_PASS' in line]
    beats = sum(int(re.search(r'checked=(\d+)',line)[1]) for line in fifo)
    check('six FIFO cases and 36005 checked beats', data['fifo']['status']=='passed' and len(fifo)==6 and beats==36005)
    arbiter = [line for line in data['arbiter']['markers'] if 'CASE_PASS' in line]
    descriptors = sum(int(re.search(r'descriptors=(\d+)',line)[1]) for line in arbiter)
    arb_beats = sum(int(re.search(r'data_beats=(\d+)',line)[1]) for line in arbiter)
    check('two AXIS arbiter cases, 256 descriptors and 10878 beats',
          data['arbiter']['status']=='passed' and len(arbiter)==2 and descriptors==256 and arb_beats==10878)
    # Preserve actual executed test sources; only explanatory comments changed
    # in the live arbiter bench after execution. Vendor RTL must be exact bytes.
    for kind in ['fifo','arbiter']:
        for entry in data[kind]['sources']:
            archived = ROOT/'results'/EVIDENCE[kind]/entry['name']
            original = Path(entry['path'])
            check('archived '+kind+' source '+entry['name'], sha(archived)==entry['sha256'])
            if original.name=='tb_adi_dmac_arb.sv':
                check('live arbiter bench only comment/space changes',
                    logical_verilog(original.read_text('utf-8'))==logical_verilog(archived.read_text('utf-8')))
            else:
                check('unchanged live '+kind+' source '+entry['name'], sha(original)==entry['sha256'])
    failure = data['failed_hot_unload']
    check('failure preserved, never accepted as rollback', bool(failure.get('candidate_error')) and
          bool(failure.get('rollback_error')) and not failure['factory_restored'])
    check('raw kernel stack retained', any('axiadc_remove' in s.get('output','') for s in failure['stages']))
    disabled = (ROOT/'experiments/p31_test_rf_overlay.py').read_text('utf-8')
    check('dangerous executable disabled without serial imports', 'return 2' in disabled and 'ChunkConsole' not in disabled and 'import serial' not in disabled)
    check('focused guard checks', data['boot_guard_tests']['status']=='focused_checks_passed')
    check('guard installed exactly', data['boot_guard_deploy']['status']=='guard_installed_backup_and_readback_verified_no_reload' and
          data['boot_guard_deploy']['new_sha256']==sha(ROOT/'board/boot/S99board')==data['boot_guard_tests']['script_sha256'])
    check('original guarded-script backup', data['boot_guard_deploy']['old_sha256']==sha(ROOT/'results'/EVIDENCE['failed_hot_unload']/'S99board-before-guard.txt'))
    check('RX profile restored', data['RX_profile_restore']['status']=='reviewed_rx_profile_restored_and_read_back')
    smoke = data['sparse_smoke']
    check('sparse smoke released, not represented as complete', smoke['status']=='receiver_abi_layout_capture_and_release_verified' and
          smoke['native_metadata']['buffer_released'] and not smoke['native_metadata']['complete_stream_saved'])
    raw = ROOT/'results'/EVIDENCE['sparse_bytes']/'prefixes.bin'
    check('65536 sparse bytes match recorded board SHA', raw.stat().st_size==65536 and sha(raw)==data['sparse_bytes']['raw']['sha256'])
    check('post-recovery idle state', data['end_state']['status']=='recovered_original_RF_both_boards_idle_and_guard_verified' and
          data['end_state']['boards']['COM8']['boot_id']==RX_BOOT and data['end_state']['serial_handles_closed'])
    check('vendor kernel sources present', data['vendor_kernel']['status']=='selected_sources_archived_for_review' and not data['vendor_kernel']['missing_required'])
    check('installed guard survived and executed in full ordinary boot',
        data['guard_full_boot']['status']=='guarded_full_warm_boot_and_three_device_readiness_verified' and
        data['guard_full_boot']['boot_id_after']==RX_BOOT and data['guard_full_boot']['ordinary_reboots_issued']==1)
    check('actual NULL instruction matched to factory kernel image',
        data['fault_instructions']['status']=='fault_instruction_matched_and_disassembled' and
        data['fault_instructions']['unique_20_byte_sequence_match'] and
        data['fault_instructions']['image_sha256']==data['kernel_image']['sha256'])
    check('bad serial transfer was rejected rather than accepted',data['rejected_whole_transfer']['status']=='failed')
    check('all 16 small chunks separately verified',len(data['sparse_bytes']['chunks'])==16 and
        all(c['attempts'][-1]['accepted'] for c in data['sparse_bytes']['chunks']))
    check('latest sparse archive belongs to final warm boot',data['sparse_bytes']['boot_id']==RX_BOOT)

    state_path = ROOT/'TX-SOURCE-STATUS.json'
    state = json.loads(state_path.read_text('utf-8'))
    evidence = {key:'results/'+folder+'/report.json' for key,folder in EVIDENCE.items()}
    state['historical_field_note'] = ('Current state is p31_current. All other phase/runtime fields retain historical scope; '
        'do not use old boot IDs or old overlay rebind instructions for current hardware. No TX application started in HW-023.')
    state['p31_current'] = dict(updated_utc=datetime.now(timezone.utc).isoformat(),
        experiment='docs/experiments/EXP-HW-023-device-tree-cdc-and-kernel-recovery.md',
        tx_boot_id=data['end_state']['boards']['COM9']['boot_id'], rx_boot_id=RX_BOOT,
        tx_recovery_directory=data['end_state']['boards']['COM9']['RAM_stage'],
        board_mode='rf', kernel_tainted=0, RX_profile='manual/0dB/2450MHz/30.72MSps/18MHz/A_BALANCED',
        RX_native_binary=smoke['remote_binary'], RX_buffer_enable=0, RX_scan_enable=[0,0,0,0],
        no_experiment_TX_or_RX_process_observed=True, serial_handles_closed=True,
        TX_application_started=False, physical_RF_silence_measured=False,
        candidate_DT_target_test_passed=False, candidate_DT_applied_to_board=False,
        original_overlay_hot_unload_crashed=True, kernel_root_cause_fixed=False,
        direct_NULL_driver_owner_fault_binary_pinned=True, exact_dirty_kernel_source_reproduced=False,
        factory_RF_recovered_after_user_power_cycle=True, hot_unload_experiment_disabled=True,
        boot_overlay_removal_retries_enabled=False, guarded_boot_script_installed=True,
        guarded_script_full_warm_boot_tested=True, guarded_failure_path_hardware_tested=False,
        cold_start_0xFF_root_cause_fixed=False,
        boot_script_sha256=sha(ROOT/'board/boot/S99board'), boot_script_backup=data['boot_guard_deploy']['backup'],
        offline_DT_checks=240, independent_BD_checks=30, negative_fixtures_detected=4,
        FIFO_digital_checked_beats=beats, AXIS_arbiter_descriptors=descriptors, AXIS_arbiter_checked_beats=arb_beats,
        CDC_critical_remaining=58, exact_FIFO_MM_endpoints_tested=False,
        external_IO_timing_complete=False, combined_bitstream_generated=False,
        combined_bitstream_programmed=False, RF_display_concurrent_hardware_accepted=False,
        lossless_stream_verified=False, real_AI_verified=False, evidence=evidence,
        checkpoint=str(out.relative_to(ROOT)/'report.json').replace('\\','/'))
    temporary = state_path.with_suffix('.p31-new')
    temporary.write_text(json.dumps(state, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    temporary.replace(state_path)

    files = [ROOT/p for p in ['START-HERE.md','README.md','TX-SOURCE-STATUS.json','board/README.md',
        'board/boot/S99board','docs/handoff/RESUME-20261019.md',
        'docs/experiments/EXP-HW-023-device-tree-cdc-and-kernel-recovery.md',
        'fpga/integration/README.md','fpga/integration/rf-display-800x480.dts',
        'fpga/tb/tb_adi_async_fifo.sv','fpga/tb/tb_adi_dmac_arb.sv','tests/test_board_rf_readiness.py',
        'results/p31-overlay-active.json','results/p31-dtc-active.json','results/p31-entry-backup.json']]
    files += sorted((ROOT/'experiments').glob('p31_*.py'))
    for folder in EVIDENCE.values():
        files += [p for p in (ROOT/'results'/folder).rglob('*') if p.is_file()]
    for path in sorted(set(files)):
        relative = path.relative_to(ROOT)
        target = out/'snapshot'/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        expected = sha(path)
        check('copied '+relative.as_posix(), sha(target)==expected)
        report['files'].append(dict(path=relative.as_posix(), bytes=path.stat().st_size, sha256=expected))
    archive = out/'p31-evidence.zip'
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as bundle:
        for row in report['files']:
            bundle.write(out/'snapshot'/row['path'], row['path'])
    report.update(status='scoped_evidence_checkpoint_verified', evidence=evidence,
        archive=dict(file=archive.name, bytes=archive.stat().st_size, sha256=sha(archive)),
        original_hot_unload_test='FAILED; candidate never loaded; recovery required user power-cycle',
        current_scope='Factory RF recovered; merged design remains offline; kernel defect not fixed')
    save()
    (ROOT/'results/p31-checkpoint-active.json').write_text(json.dumps(dict(report=str(out/'report.json')),indent=2)+'\n',encoding='utf-8')
    print(out)
    print(report['status'], len(report['checks']), 'checks', len(report['files']), 'files')


if __name__ == '__main__':
    main()
