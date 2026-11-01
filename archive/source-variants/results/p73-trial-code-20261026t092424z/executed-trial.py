"""Known-source RF regression of accepted P67 binary. No model/boot/PL edits."""
import argparse,json,re,time,uuid
from datetime import datetime,timezone
from pathlib import Path
from p45_checkpoint import ROOT,read,write,sha,rel
from p67_board_trial import control
from p35_uart_files import upload
from p52_ram import board_ram_tmp
from p46_known_source import GUARD_SHA
from p72_capture_uncertain import archive
from rfsig.board_session import require_rx_control,require_tx_off,source_directory,one_json

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--link-confirmation',required=True,type=Path);ap.add_argument('--build',required=True,type=Path);ap.add_argument('--review',required=True,type=Path);a=ap.parse_args()
    human=read(a.link_confirmation)
    if human.get('user_answer')!='仍是原接法，衰减连接未变' or not human.get('unchanged_TX1_attenuation_RX1A'):raise ValueError('current physical link confirmation required')
    build_path=a.build;build=read(build_path);proof=read(a.review)
    if (build['status']!='built_P73_event_diagnostic_offline_tests_pending'
        or proof['status']!='passed_P73_bounded_same_update_capture_and_frozen_policy'
        or proof['build_sha256']!=sha(build_path)):raise ValueError('P73 reviewed instrumentation required')
    if sha(ROOT/build['binary'])!=build['binary_sha256']:raise ValueError('P69 binary changed')
    for p,h in build['inputs_sha256'].items():
        if sha(ROOT/p)!=h:raise ValueError('P69 input changed '+p)
    cache=read(ROOT/'results/p59-source-active.json');source_path=ROOT/cache['report'];upload_report=read(source_path)
    if sha(source_path)!=cache['report_sha256'] or upload_report['status']!='passed_P59_prepare-source':raise ValueError('current source restoration required')
    source=upload_report['source']
    if sha(ROOT/source['source_report'])!=source['source_report_sha256']:raise ValueError('source provenance changed')
    with control.operation_lock():
        c=control.Controller('p73-native-events');print(c.out,flush=True)
        c.record.update(build=rel(build_path),build_sha256=sha(build_path),link_confirmation=rel(a.link_confirmation),
            link_confirmation_sha256=sha(a.link_confirmation),source_upload=rel(source_path),source_upload_sha256=sha(source_path),
            diagnostic_protocol=dict(early_late_same_calibration=True,late_age_s=160,fixed_shots_s=[8],extra_uncertain_shots_per_phase=0,native_events=dict(maximum=12,per_state_age=3,onset_guard_s=2,minimum_same_state_gap_s=2,age_boundary_s=120),trigger_saved_state_may_differ=True,model_or_policy_change=False),duration_ms=300000,segments=[],samples=[],shots=[],chunks=[],candidate_started=False,
            RF_transmissions=0,scope='exposed seed2315 controlled deployment regression, not independent AI accuracy',
            acceptance_protocol=dict(minimum_coverage=.70,minimum_conditional_accuracy=.90,
                stable_after_first_sample_s=2,stable_end_margin_s=3,pilot_and_background_must_abstain=True))
        running=False;pending=None;pid=None;rx_boot=None;stage=None
        try:
            c.status();tx_info=c.record['boards']['TX'];rx_info=c.record['boards']['RX']
            require_tx_off(tx_info);require_rx_control(rx_info,running=False)
            directory=source_directory(source,tx_info['boot_id']);rx_boot=rx_info['boot_id']
            c.record.update(initial_TX=tx_info,initial_RX=rx_info);c.save()
            with c.board('RX') as (rx,identity),c.board('TX') as (tx,tx_identity):
                fresh=c.inspect('RX',rx,identity);require_rx_control(fresh,running=False)
                fresh_tx=c.inspect('TX',tx,tx_identity);require_tx_off(fresh_tx)
                if fresh['boot_id']!=rx_boot or fresh_tx['boot_id']!=tx_info['boot_id']:raise ValueError('boot changed')
                if c.digest(tx,directory+'/guard')!=GUARD_SHA:raise ValueError('guard changed')
                c.record['RAM_tmp']=board_ram_tmp(rx)
                stage='/tmp/p35-p73-'+datetime.now(timezone.utc).strftime('%H%M%S')
                c.record['stage']=stage;c.save()
                rx.command('s='+stage);rx.command('test ! -e $s');rx.command('mkdir $s')
                rx.command("PS1='# '");upload(rx,stage+'/a',(ROOT/build['binary']).read_bytes())
                rx.command("PS1=''");rx.command('stty -echo')
                if c.digest(rx,stage+'/a')!=build['binary_sha256']:raise ValueError('upload digest mismatch')
                rx.command('chmod 755 $s/a');rx.command('o=$s/data')
                rx.command('export P56_CONTROL_FILE=$s/control P56_SHOT_FILE=$s/shot')
                rx.command('test ! -e $s/control');rx.command('export P73_EVENT_CAPTURE=1')
                rx.command('timeout -k 2 330 $s/a $o 300000 500 >$s/log 2>&1 &')
                rx.command('pid=$!; echo $pid >$s/pid');pid=int(rx.value(stage+'/pid'));running=True
                c.record.update(candidate_started=True,owned_timeout_pid=pid,status='P69_RX_running');c.save()
                began=time.monotonic()
                def sample():
                    row=one_json(c.optional(rx,stage+'/data/ai.json'));c.record['samples'].append(row)
                    if row.get('ready') and 'calibration_ready_elapsed' not in c.record:c.record['calibration_ready_elapsed']=row['elapsed_s']
                    c.save();return row
                def wait_for(predicate,limit=12):
                    end=time.monotonic()+limit
                    while time.monotonic()<end:
                        row=sample()
                        if predicate(row):return row
                        time.sleep(.5)
                    raise ValueError('RX policy state deadline')
                def shot(label,trigger=None):
                    number=len(c.record['shots'])+1
                    if number>16:raise ValueError('native snapshot budget exceeded')
                    rx.command('echo '+str(number)+' >$s/shot')
                    path=stage+'/data/shot-'+format(number,'02d')+'.json';end=time.monotonic()+8
                    while time.monotonic()<end:
                        data=one_json(c.optional(rx,path),optional=True)
                        if data:
                            c.record['shots'].append(dict(id=number,label=label,trigger=trigger,AI=data));c.save();return
                        time.sleep(.5)
                    raise ValueError('snapshot request deadline')
                wait_for(lambda row:row['state']=='CALIBRATION_REQUIRED')
                token=uuid.uuid4().hex;c.record['calibration_token']=token
                rx.command('b='+rx_boot);rx.command('m='+read(ROOT/build['frozen'])['frozen_inputs']['model']['sha256'])
                rx.command('k='+token);rx.command('printf "P56CAL1 %s %s %s\\n" $b $m $k >$s/control.next')
                rx.command('mv $s/control.next $s/control');wait_for(lambda row:row['state']=='WAIT_PILOT');shot('background-before-pilot')
                def finish_tx():
                    nonlocal pending
                    if pending is None:return
                    case=pending;marker=case['marker'];transcript=case.get('start_stdout','')
                    end=case['host_start']+case['seconds']+15
                    while not re.search(r'^'+marker+r':\d+\r?$',transcript,re.M) and time.monotonic()<end:
                        transcript+=tx.read(2,r'^'+marker+r':\d+\r?$')
                    case['end_stdout']=transcript
                    case['cleanup_verified']=bool(re.search(r'^'+marker+r':0\r?$',transcript,re.M)
                        and 'TX_CLEANUP buffer_released=true rf_settings_written=false status=0' in transcript
                        and 'DDS_ZERO_SOURCE_READBACK=PASS' in transcript)
                    c.save()
                    if not case['cleanup_verified']:raise ValueError('TX cleanup unconfirmed')
                    ending=c.inspect('TX',tx,tx_identity);require_tx_off(ending)
                    if ending['RF']!=tx_info['RF'] or ending['boot_id']!=tx_info['boot_id']:raise ValueError('TX state changed')
                    pending=None
                for phase,name,seconds in [('pilot','tone',15),('early','qam16',45),('late','qam16',45)]:
                    if phase=='late':
                        while True:
                            row=sample()
                            if row['elapsed_s']>=c.record['calibration_ready_elapsed']+160:break
                            if row['state']=='STOPPED':raise ValueError('RX ended before late window')
                            time.sleep(3)
                    if name!='tone':wait_for(lambda row:row['ready'] and row['state']=='NO_USABLE_SIGNAL')
                    check=c.inspect('TX',tx,tx_identity);require_tx_off(check)
                    if check['boot_id']!=tx_info['boot_id']:raise ValueError('TX rebooted')
                    if c.digest(tx,directory+'/'+name)!=source['files_sha256'][name]:raise ValueError('waveform changed')
                    row=sample()
                    if name=='tone' and (row['state']!='WAIT_PILOT' or row['ready']):raise ValueError('pilot requires fresh background')
                    if name!='tone' and (not row['ready'] or row['calibration_token']!=token):raise ValueError('fresh calibration required')
                    tx.command('cd '+directory);tx.command('p='+name);tx.command('h='+source['files_sha256'][name])
                    tx.command('b=boot-session:'+tx_info['boot_id']);tx.command('n=131072; f=30720000; l=2450000000; w=18000000')
                    marker='__P69_TX_'+uuid.uuid4().hex[:8]+'__'
                    command='./guard --run $p $n $f $l $w -10 '+str(seconds)+' $b A $h RF_LINK_REVIEWED'
                    if len(command)>72:raise ValueError('TX line too long')
                    case=dict(phase=phase,name=name,seconds=seconds,marker=marker,expected_class={'bpsk':0,'qpsk':1,'qam16':2}.get(name,-1),cleanup_verified=False)
                    c.record['segments'].append(case);pending=case;case['host_start']=time.monotonic();c.save()
                    tx.port.write((command+"\rprintf '\\n"+marker+":%s\\n' \"$?\"\r").encode('ascii'))
                    case['start_stdout']=tx.read(8,r'CYCLIC_PUSH_SUBMITTED samples=131072 deadline_seconds='+str(seconds))
                    if 'CYCLIC_PUSH_SUBMITTED samples=131072 deadline_seconds='+str(seconds) not in case['start_stdout']:raise ValueError('TX start unconfirmed')
                    c.record['RF_transmissions']+=1;anchor=sample()['elapsed_s'];case['score_start_s']=anchor+2;case['score_end_s']=anchor+seconds-3;c.save()
                    print('P69 RF '+name+' '+str(seconds)+' seconds',flush=True)
                    captured=False
                    while time.monotonic()-case['host_start']<seconds:
                        row=sample();elapsed=time.monotonic()-case['host_start']
                        if elapsed>=(6 if name=='tone' else 8) and not captured:
                            shot(phase+'-fixed',row);captured=True
                        time.sleep(.5)
                    finish_tx();wait_for(lambda row:row['ready'] and row['state']=='NO_USABLE_SIGNAL')
                shot('background-after-signals');c.record.update(status='P69_RX_running_calibrated_background');c.save()
                while time.monotonic()-began<325:
                    row=sample();print('P69 RX '+str(round(row['elapsed_s']))+'s '+row['state'],flush=True)
                    if row['state']=='STOPPED':break
                    time.sleep(5)
                else:raise TimeoutError('RX duration exceeded')
                rx.command('wait $pid',timeout=10);running=False
                summary=one_json(c.optional(rx,stage+'/data/summary.json'));ai=one_json(c.optional(rx,stage+'/data/ai.json'))
                c.record.update(native_summary=summary,final_AI=ai)
                if (summary['status']!='pass' or summary['reason']!='duration_complete'
                    or summary['display_revision']!='p73' or not summary['buffer_released'] or not summary['context_released']
                    or not summary['worker_joined'] or not summary['RF_after_matches'] or summary['cleanup_unconfirmed']
                    or ai['state']!='STOPPED' or ai['accepted_class']!=-1):raise ValueError('RX cleanup/evidence differs')
                ending=c.inspect('RX',rx,identity);require_rx_control(ending,running=False)
                end_tx=c.inspect('TX',tx,tx_identity);require_tx_off(end_tx)
                if ending['boot_id']!=rx_boot or ending['profile_hashes']!=rx_info['profile_hashes']:raise ValueError('RX baseline changed')
                c.record.update(after_RX=ending,after_TX=end_tx,TX_stopped=True,RX_stopped=True);c.save()
                names=['dashboard.json','ai.json','ai-history.jsonl','summary.json','last-display-packed.bin','fb.raw','metrics.json','metrics-history.jsonl']
                for item in c.record['shots']:
                    names.extend('shot-'+format(item['id'],'02d')+'.'+ext for ext in ('json','bin','metrics.json'))
                uncertain=[s for s in c.record['shots'] if s['AI']['state']=='UNCERTAIN']
                accepted=[s for s in c.record['shots'] if s['AI']['state']=='CLASSIFIED']
                chosen=(uncertain[:1]+accepted[:1])
                if len(chosen)<2:chosen+= [s for s in c.record['shots'] if s not in chosen][:2-len(chosen)]
                c.record['framebuffer_shot_ids']=[s['id'] for s in chosen]
                names.extend('shot-'+format(s['id'],'02d')+'.raw' for s in chosen)
                event_text=c.optional(rx,stage+'/data/event-history.jsonl')
                events=[json.loads(line) for line in event_text.splitlines() if line.startswith('{')]
                if not 1<=len(events)<=12 or [v['id'] for v in events]!=list(range(1,len(events)+1)):raise ValueError('native event manifest invalid')
                c.record['events']=events;c.save();names.append('event-history.jsonl')
                for e in events:names.extend('event-'+format(e['id'],'02d')+'.'+ext for ext in ('bin','json','metrics.json'))
                archive(c,rx,stage,names)
                c.record.update(status='passed_P73_native_events_archived_pending_independent_review',persistent_profile_changed=False)
        except Exception as e:
            c.record.update(status='failed_or_unconfirmed_P73_native_events',error=repr(e));c.save()
            # Every RF operation is bounded by the native guard. Never issue a
            # second TX or kill an unowned process after an uncertain completion.
            if pending:
                remaining=max(0,pending['seconds']+3-(time.monotonic()-pending['host_start']))
                if remaining:time.sleep(min(remaining,60))
                c.record['TX_guard_deadline_waited']=True
            if running and pid and stage:
                try:
                    with c.board('RX') as (b,identity):
                        if b.value('/proc/sys/kernel/random/boot_id')!=rx_boot:raise ValueError('boot changed')
                        cmd=b.command('tr "\\000" " " </proc/'+str(pid)+'/cmdline')
                        if stage+'/a' not in cmd:raise ValueError('owned command differs')
                        b.command('kill -TERM '+str(pid));time.sleep(4)
                        c.record['error_cleanup_RX']=c.inspect('RX',b,identity)
                except Exception as cleanup:c.record['cleanup_error']=repr(cleanup)
        c.record['serial_closed']=True;c.save();print(c.record['status'],flush=True)
        return int(not c.record['status'].startswith('passed'))
if __name__=='__main__':raise SystemExit(main())
