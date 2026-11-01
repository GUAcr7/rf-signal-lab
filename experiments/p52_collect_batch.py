"""Bounded per-seed real RF collection; test acquisition requires a frozen model."""
import argparse,json,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
from p45_checkpoint import ROOT,read,write,sha,rel
from p46_restore_tx import validate_source_package

def main():
    p=argparse.ArgumentParser()
    for key in ('plan','preflight','rx-smoke'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--roles',nargs='+',choices=['train','validation','test'],default=['train','validation'])
    p.add_argument('--first-source',type=Path);p.add_argument('--frozen-model',type=Path)
    p.add_argument('--resume-from',type=Path);p.add_argument('--quarantine',type=Path)
    args=p.parse_args();plan=read(args.plan);preflight=read(args.preflight);smoke=read(args.rx_smoke)
    if plan['status']!='frozen_before_new_RF_acquisition' or preflight['status']!='read_only_both_boards_identified_DMA_idle':raise ValueError('frozen plan and idle preflight required')
    if smoke['status']!='passed_finite_full_returned_buffers_board_only_pending_host_retrieval' or not smoke['independent_final_idle_verified']:raise ValueError('same-boot full RX smoke required')
    if smoke['expected_boot']!=preflight['boards']['COM8']['boot_id']:raise ValueError('mixed boot')
    if 'test' in args.roles:
        if args.roles!=['test'] or not args.frozen_model:raise ValueError('test collected separately after model freeze')
        frozen=read(args.frozen_model)
        if frozen['status']!='frozen_real_RF_model_before_unseen_test_capture':raise ValueError('frozen real model required')
        if sha(args.plan)!=frozen['frozen_inputs']['plan']['sha256']:raise ValueError('test plan differs from frozen model protocol')
        for v in frozen['frozen_inputs'].values():
            if sha(ROOT/v['path'])!=v['sha256']:raise ValueError('frozen model/pipeline changed')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p52-batch-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    inputs=[args.plan,args.preflight,args.rx_smoke,ROOT/'experiments/p52_capture_sources.py',ROOT/'experiments/p52_restore_tx.py',
        ROOT/'experiments/p52_analyse_sources.py',ROOT/'src/rfsig/real_rf_reference.py',ROOT/'src/rfsig/rf_ai_input.py',ROOT/'src/rfsig/rf_ai_calibration.py']
    r=dict(status='collecting_REAL_RF',created_utc=datetime.now(timezone.utc).isoformat(),roles=args.roles,plan=rel(args.plan),plan_sha256=sha(args.plan),groups=[],stages=[],
        expected_boot=smoke['expected_boot'],TX_expected_boot=preflight['boards']['COM9']['boot_id'],
        input_sha256={rel(f):sha(f) for f in inputs},frozen_model=rel(args.frozen_model) if args.frozen_model else None,
        frozen_model_sha256=sha(args.frozen_model) if args.frozen_model else None,
        new_RF_buffers=0,independent_real_RF_accuracy='not_yet_evaluated',
        PL_changes=False,RF_attribute_writes=False,TX_peak_component_counts=256,TX_hardwaregain_db=-10,TX_seconds_each=15,
        serial_closed=True,all_completed_TX_cleanup_verified=True,startup_paused_for_archiving=True)
    r['current_TX_cleanup_verified']=True
    if args.resume_from or args.quarantine:
        if not args.resume_from or not args.quarantine or args.roles!=['train','validation'] or args.first_source:raise ValueError('only explicit reviewed training/validation transport resume allowed')
        prior=read(args.resume_from);quarantine=read(args.quarantine);failed=read(ROOT/quarantine['failed_trial'])
        if (prior['status']!='failed_or_unconfirmed_batch_stop' or prior['plan_sha256']!=r['plan_sha256']
            or prior['expected_boot']!=r['expected_boot'] or prior['TX_expected_boot']!=r['TX_expected_boot']
            or quarantine['status']!='preserved_partial_transport_failure_not_used_for_AI'
            or 'ClearCommError' not in failed['error'] or failed['split']!='validation'
            or sha(ROOT/quarantine['failed_trial'])!=quarantine['failed_trial_sha256']):raise ValueError('specific archived transport failure required')
        for path,digest in prior['input_sha256'].items():
            if sha(ROOT/path)!=digest:raise ValueError('original collection contract changed')
        for group in prior['groups']:
            if group.get('status')=='all_buffers_archived_and_known_source_quality_passed':
                for key in ('source','trial','archives','quality'):
                    path=group['source_report'] if key=='source' else group[key]
                    if sha(ROOT/path)!=group[key+'_sha256']:raise ValueError('retained group evidence changed')
                r['groups'].append(group)
            elif group['seed']!=failed['seed']:raise ValueError('unexplained incomplete prior group')
        r.update(resume_parent=rel(args.resume_from),resume_parent_sha256=sha(args.resume_from),
            quarantine=rel(args.quarantine),quarantine_sha256=sha(args.quarantine),
            resume_reason='Windows ClearCommError; same boot independently idle, partial raw archived, no model fitted or test exposed',
            new_RF_buffers=len(r['groups'])*4*plan['blocks_per_case'],retained_prior_complete_groups=len(r['groups']))
    def save():
        write(out/'report.json',r)
        state=read(ROOT/'TX-SOURCE-STATUS.json');state.update(status=r['status'],authoritative_current_field='p52_current')
        state['p52_current']=dict(report=rel(out/'report.json'),status=r['status'],expected_boot=r['expected_boot'],serial_closed=r['serial_closed'],startup_paused_for_archiving=True,
            RX_idle='unverified_after_failure' if r['status'].startswith('failed_') else 'child_running_recheck' if not r['serial_closed'] else True,
            current_TX_cleanup_verified=r['current_TX_cleanup_verified'],AI_model_accepted=False,live_AI_on_LCD=False)
        write(ROOT/'TX-SOURCE-STATUS.json',state);write(ROOT/'results/p52-active.json',state['p52_current'])
    def run(label,script,status,*params,timeout=400):
        if label.endswith('-capture'):r['current_TX_cleanup_verified']=False
        print(label,flush=True);r.update(status=label,serial_closed=False);save()
        stdout=out/(label+'.stdout');stderr=out/(label+'.stderr')
        with stdout.open('wb') as a,stderr.open('wb') as b:
            child=subprocess.run([sys.executable,str(ROOT/'experiments'/script),*map(str,params)],cwd=ROOT,stdout=a,stderr=b,timeout=timeout)
        r['serial_closed']=True
        stage=dict(label=label,exit_code=child.returncode);r['stages'].append(stage);save()
        paths=[Path(s.strip())/'report.json' for s in stdout.read_text('utf-8').splitlines() if Path(s.strip()).is_absolute() and (Path(s.strip())/'report.json').is_file()]
        if child.returncode or len(paths)!=1:raise ValueError(label+' failed; all evidence retained')
        value=read(paths[0]);stage.update(report=rel(paths[0]),report_sha256=sha(paths[0]));save()
        if value['status']!=status:raise ValueError(label+' status unaccepted')
        if label.endswith('-capture'):r['current_TX_cleanup_verified']=bool(value['all_TX_cleanup_verified']);save()
        return paths[0],value
    save();(out/'executed.py').write_bytes(Path(__file__).read_bytes())
    try:
        retained_seeds={g['seed'] for g in r['groups']}
        for index,item in enumerate(g for g in plan['groups'] if g['role'] in args.roles and g['seed'] not in retained_seeds):
            for f,digest in r['input_sha256'].items():
                if sha(ROOT/f)!=digest:raise ValueError('collection input changed')
            package=ROOT/item['package'];validate_source_package(package)
            if sha(package)!=item['package_sha256']:raise ValueError('source package changed')
            row=dict(seed=item['seed'],role=item['role'],capture_session=item['planned_capture_session']);r['groups'].append(row);save()
            prefix=str(item['seed'])
            if index==0 and args.first_source:
                source=args.first_source;restored=read(source)
                if restored['source_report_sha256']!=sha(package) or restored['expected_boot']!=r['TX_expected_boot'] or restored['RX_expected_boot']!=r['expected_boot']:raise ValueError('first source mismatch')
            else:
                source,restored=run(prefix+'-restore','p52_restore_tx.py','guard_and_peak256_sources_restored_inspected_checked_no_TX',
                    '--source-report',package,'--preflight',args.preflight)
            row.update(source_report=rel(source),source_sha256=sha(source));save()
            cases=[v for name in item['case_order'] for v in ('--case',name)]
            capture,captured=run(prefix+'-capture','p52_capture_sources.py','passed_bounded_known_source_captures_pending_host_archive',
                '--plan',args.plan,'--source-report',source,'--rx-smoke',args.rx_smoke,'--blocks',plan['blocks_per_case'],*cases,timeout=240)
            if not captured['all_TX_cleanup_verified'] or not captured['independent_final_RX_idle'] or not captured['serial_closed']:raise ValueError('cleanup unconfirmed')
            row.update(trial=rel(capture),trial_sha256=sha(capture));r['new_RF_buffers']+=4*plan['blocks_per_case'];save()
            archives,_=run(prefix+'-archives','p46_archive_cases.py','passed_all_known_source_raw_buffers_archived','--trial',capture,timeout=1500)
            row.update(archives=rel(archives),archives_sha256=sha(archives));save()
            analysis,_=run(prefix+'-quality','p52_analyse_sources.py','passed_all_known_source_snapshot_quality','--archives',archives,timeout=240)
            row.update(quality=rel(analysis),quality_sha256=sha(analysis),status='all_buffers_archived_and_known_source_quality_passed');save()
            print('Completed real RF seed '+prefix,flush=True)
        r['status']='passed_all_planned_REAL_RF_groups_archived_and_quality_checked'
    except Exception as e:r.update(status='failed_or_unconfirmed_batch_stop',error=repr(e))
    save();print(out);print(r['status'])
    return 0 if r['status'].startswith('passed_') else 1
if __name__=='__main__':raise SystemExit(main())
