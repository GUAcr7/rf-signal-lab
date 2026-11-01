"""P79 computer-mediated TJC control, fixed reviewed RF presets only.

The screen does not connect directly to P201. USB-TTL and this computer must
remain connected. No screen text is used as a shell command or RF parameter.
"""
from pathlib import Path
from datetime import datetime,timezone
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import argparse
import hashlib
import json
import queue
import re
import sys
import threading
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'experiments'),str(ROOT/'host')]
import board_control as control
from source_screen_link import Screen,resolve_screen
from serial.tools import list_ports
from rfsig.source_screen import PanelSelection,BUTTONS
from rfsig.board_session import require_signal_ready,require_tx_off,source_directory,one_json,WORK

NAMES=('tone','bpsk','qpsk','qam16')

class Cancelled(Exception):pass

def validate_request(signal,seconds):
    if signal not in NAMES or type(seconds)!=int or not 8<=seconds<=60:
        raise ValueError('Only four reviewed presets and 8..60 whole seconds allowed')

def cleanup_proven(log,exit_code):
    return (exit_code==0 and
            bool(re.search(r'^TX_CLEANUP buffer_released=true rf_settings_written=false status=0\r?$',log,re.M)) and
            bool(re.search(r'^DDS_ZERO_SOURCE_READBACK=PASS\r?$',log,re.M)))

def require_not_cancelled(cancel):
    if cancel.is_set():raise Cancelled('Cancelled before launch; no RF requested')

def precheck(c,signal,seconds,cancel):
    validate_request(signal,seconds);require_not_cancelled(cancel)
    c.status();require_not_cancelled(cancel)
    tx,rx=c.record['boards']['TX'],c.record['boards']['RX']
    require_tx_off(tx);require_signal_ready(rx,signal)
    cache=json.loads((ROOT/'results/p59-source-active.json').read_text('utf-8'))
    path=ROOT/cache['report']
    if control.sha(path)!=cache['report_sha256']:raise ValueError('Source report changed')
    source_report=json.loads(path.read_text('utf-8'))
    if source_report['status']!='passed_P59_prepare-source':raise ValueError('Source bank is not accepted')
    source=source_report['source'];directory=source_directory(source,tx['boot_id'])
    if control.sha(ROOT/source['source_report'])!=source['source_report_sha256']:
        raise ValueError('Source origin changed')
    c.record['source_upload_report']=cache
    return tx,rx,source,directory

def accepted_receipt(receipt,nonce,boot,signal,seconds):
    if not isinstance(receipt,dict):return False
    expected=dict(schema='rfsig.source_job.v1',nonce=nonce,boot_id=boot,
                  signal=signal,seconds=seconds,identity_valid=True,child_reaped=True)
    return (all(type(receipt.get(k)) is type(v) and receipt.get(k)==v for k,v in expected.items())
            and type(receipt.get('child_pid')) is int and receipt['child_pid']>1
            and isinstance(receipt.get('start_ticks'),str) and receipt['start_ticks'].isdigit()
            and type(receipt.get('exit_code')) is int)

def detached_run(c,t,b,tx,source,directory,signal,seconds,cancel,notifications):
    """RAM-only isolated supervisor; durable receipt instead of a login-shell wait."""
    from rfsig.console_transfer import upload_uudecode
    template=ROOT/'board/source-job.sh';payload=template.read_bytes()
    if b'\r' in payload:raise ValueError('Supervisor requires exact LF bytes')
    digest=control.sha(template);script='sj-'+digest[:12]+'.sh'
    (c.out/'source-job.sh').write_bytes(payload)
    c.record['supervisor_sha256']=digest
    t.command('d='+directory);t.command('a=$d/'+script)
    present=t.command('if test -e $a;then echo __EXISTS__;fi')
    if '__EXISTS__' not in present:
        c.record['supervisor_upload']=(t.upload(payload,directory+'/'+script) if hasattr(t,'upload')
                                       else upload_uudecode(t,payload,directory+'/'+script))
    if c.digest(t,directory+'/'+script)!=digest:raise ValueError('Supervisor bytes changed')
    t.command('test -x /bin/busybox');t.command('x=/bin/busybox')
    available=t.command('$x --list | grep -E "^setsid$"')
    if not re.search(r'^setsid\r?$',available,re.M):
        raise ValueError('Required explicit BusyBox applets absent')
    nonce=uuid.uuid4().hex[:8];jobdir=directory+'/job-'+nonce
    t.command('j='+jobdir);t.command('test ! -e $j');t.command('mkdir -m 700 $j')
    t.command('k='+tx['boot_id']);t.command('h='+source['files_sha256'][signal])
    t.command('set -- $d $j '+signal+' '+str(seconds)+' $k $h '+nonce)
    t.command('o=$j/supervisor.log')
    monitor=t.command('case $- in *m*) echo __MONITOR_ON__;;*) echo __MONITOR_OFF__;;esac')
    restore_monitor='__MONITOR_ON__' in monitor
    require_not_cancelled(cancel)
    c.record.update(job_directory=jobdir,job_nonce=nonce,RF_transmissions_requested=1,
                    TX_cleanup_verified=False,AI_observations=[],interactive_job_control_temporarily_disabled=True)
    submitted=False;stop_sent=False;receipt=None;started=time.monotonic();last_ai=0
    try:
        t.command('set +m')
        require_not_cancelled(cancel)
        t.command('$x setsid /bin/sh $a "$@" </dev/null >$o 2>&1 &')
        c.record['detached_launch_acknowledged']=True;c.save()
        deadline=time.monotonic()+seconds+18
        while time.monotonic()<deadline:
            transcript=c.optional(t,jobdir+'/native.log')
            if 'CYCLIC_PUSH_SUBMITTED samples=131072 deadline_seconds='+str(seconds) in transcript and not submitted:
                submitted=True;c.record['RF_transmissions']=1
                notifications.put(dict(kind='submitted',signal=signal))
            receipt=one_json(c.optional(t,jobdir+'/receipt.json'),optional=True)
            if receipt is not None:break
            if cancel.is_set() and not stop_sent:
                if t.value('/proc/sys/kernel/random/boot_id')!=tx['boot_id']:
                    raise ValueError('TX boot changed before STOP request')
                t.command(': >$j/stop');stop_sent=True
                c.record.update(STOP_requested=True,STOP_sent_monotonic=time.monotonic())
            if submitted and time.monotonic()-last_ai>=.5:
                c.record['AI_observations'].append(one_json(c.optional(b,WORK+'/data/ai.json')))
                last_ai=time.monotonic()
            c.save();time.sleep(.1)
        transcript=c.optional(t,jobdir+'/native.log')
        c.record.update(TX_transcript=transcript,supervisor_receipt=receipt,
                        supervisor_elapsed_host_s=time.monotonic()-started)
        if not accepted_receipt(receipt,nonce,tx['boot_id'],signal,seconds):
            raise ValueError('Fresh detached native-child receipt not confirmed')
        c.record['TX_exit_code']=receipt['exit_code']
        c.record['TX_cleanup_verified']=cleanup_proven(transcript,receipt['exit_code'])
        if stop_sent and not (receipt.get('stop_seen') is True and receipt.get('signal_sent') is True):
            raise ValueError('STOP was requested but its execution is unconfirmed')
        c.save()
        return dict(submitted=submitted,cancelled=stop_sent)
    finally:
        if restore_monitor:
            try:t.command('set -m');c.record['interactive_job_control_restored']=True
            except Exception as error:c.record['job_control_restore_error']=repr(error)
        c.save()

def job(kind,signal,seconds,cancel,notifications):
    """Sole owner of board serial handles; UI thread can always request STOP."""
    validate_request(signal,seconds)
    from p201_usb_network import PanelController
    c=PanelController('p79-panel-'+kind);print(c.out,flush=True)
    (c.out/'source_screen_rf.py').write_bytes(Path(__file__).read_bytes())
    c.record.update(computer_bridge_only=True,signal=signal,seconds=seconds,TX_cleanup_verified=False)
    pending=False;submitted=False;transcript='';requested_stop=False
    try:
        tx,rx,source,directory=precheck(c,signal,seconds,cancel)
        with c.board('TX') as (t,identity):
            fresh=c.inspect('TX',t,identity);require_tx_off(fresh)
            if fresh['boot_id']!=tx['boot_id']:raise ValueError('TX rebooted')
            if c.digest(t,directory+'/guard')!=control.GUARD_SHA:raise ValueError('TX guard changed')
            if c.digest(t,directory+'/'+signal)!=source['files_sha256'][signal]:raise ValueError('Waveform changed')
            require_not_cancelled(cancel)
            if kind=='check':
                c.record['status']='passed_P79_apply_checks_no_RF'
                return dict(kind=kind,passed=True,report=str((c.out/'report.json').relative_to(ROOT)))
            with c.board('RX') as (b,rx_identity):
                current=c.inspect('RX',b,rx_identity);require_signal_ready(current,signal)
                if current['boot_id']!=rx['boot_id'] or current['AI']['calibration_token']!=rx['AI']['calibration_token']:
                    raise ValueError('RX session changed')
                require_not_cancelled(cancel)
                require_not_cancelled(cancel)
                result=detached_run(c,t,b,tx,source,directory,signal,seconds,cancel,notifications)
                submitted=result['submitted'];requested_stop=result['cancelled']
                if not submitted:raise ValueError('No native submission receipt')
                if not c.record['TX_cleanup_verified']:raise ValueError('Native cleanup not confirmed')
                final_tx=c.inspect('TX',t,identity);require_tx_off(final_tx)
                final_rx=c.inspect('RX',b,rx_identity)
                if final_tx['RF']!=fresh['RF']:raise ValueError('RF settings changed')
                c.record.update(after_TX=final_tx,after_RX=final_rx)
                if signal=='tone' and not requested_stop and not final_rx['AI'].get('ready'):
                    raise ValueError('Pilot did not complete calibration')
                c.record['status']='passed_P79_guarded_panel_TX_cancelled_cleanly' if requested_stop else 'passed_P79_guarded_panel_TX_deadline_cleanly'
                return dict(kind=kind,passed=True,signal=signal,cancelled=requested_stop,
                            report=str((c.out/'report.json').relative_to(ROOT)))
    except Cancelled as error:
        c.record.update(status='cancelled_P79_before_RF',error=str(error))
        return dict(kind=kind,passed=True,cancelled=True,before_RF=True,
                    report=str((c.out/'report.json').relative_to(ROOT)))
    except Exception as error:
        c.record.update(status='failed_or_unconfirmed_P79_panel_job',error=repr(error),
                        pending_child_unconfirmed=bool(c.record.get('detached_launch_acknowledged') and not c.record.get('TX_cleanup_verified')))
        return dict(kind=kind,passed=False,error=repr(error),report=str((c.out/'report.json').relative_to(ROOT)))
    finally:
        c.record['serial_closed']=True;c.save()

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--preflight',type=Path,required=True)
    ap.add_argument('--rf-link-reviewed',action='store_true')
    ap.add_argument('--tx-job-transport',choices=('usb-network',),required=True,
                    help='Explicit verified same-USB network task control; fixed serial entry stays unchanged')
    ap.add_argument('--seconds',type=int,default=600)
    ap.add_argument('--initial-signal',choices=NAMES,default='tone')
    ap.add_argument('--required-signals',choices=NAMES,nargs='+',default=list(NAMES))
    ap.add_argument('--require-stop-test',action='store_true')
    ap.add_argument('--protocol-regression',action='store_true',
                    help='Explicit automated bench replay via panel printh, never claim finger/click testing')
    args=ap.parse_args()
    if not args.rf_link_reviewed or not 30<=args.seconds<=900:
        ap.error('Require original confirmed RF link and 30..900s session')
    proof=json.loads(args.preflight.read_text('utf-8'))
    if proof.get('status')!='passed_P78_readonly_boards_and_teammate_screen_identity':
        raise ValueError('P78 physical identity proof required')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p79-screen-control-%Y%m%dT%H%M%SZ');out.mkdir()
    record=dict(status='running_P79_screen_RF_control',computer_bridge_only=True,
                direct_P201_UART=False,physical_events=[],jobs=[],events=[],serial_closed=False,
                preflight_sha256=control.sha(args.preflight),human_RF_link='2026-10-27 user confirmed original coax/attenuation unchanged',
                required_signals=sorted(set(args.required_signals)),require_stop_test=args.require_stop_test,
                input_origin='screen_generated_protocol_replay' if args.protocol_regression else 'human_finger')
    (out/'executed.py').write_bytes(Path(__file__).read_bytes())
    def save():(out/'report.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    def log(kind,**data):record['events'].append(dict(kind=kind,utc=datetime.now(timezone.utc).isoformat(),**data));save()
    screen=None;future=None;cancel=threading.Event();messages=queue.Queue();panel=PanelSelection()
    panel.signal=NAMES.index(args.initial_signal)
    status='IDLE';generation=0;job_generation=0;job_cancel_reason=None;fault=False;began=time.monotonic();last_heartbeat=0
    driver=None
    if args.protocol_regression:
        from rfsig.source_screen_regression import ProtocolRegression
        driver=ProtocolRegression()
    with control.operation_lock(),ThreadPoolExecutor(max_workers=1) as pool:
        try:
            screen=Screen(resolve_screen(proof,list_ports.comports()),out/'UART',log)
            record['identity']=screen.identify();screen.query('sendme','page',b'\x00')
            screen.fields(panel.fields(status));print(out,flush=True)
            print('P79 READY. Select -> APPLY -> wait READY -> START. Real bounded RF enabled.',flush=True)
            while time.monotonic()-began<args.seconds:
                if driver:
                    if fault:raise RuntimeError('Protocol regression backend fault')
                    button=driver.next_button(status,future is not None,time.monotonic())
                    if button is not None:
                        log('protocol_regression_step',index=driver.index,button=button)
                        screen.replay(button)
                screen.events()
                while screen.touches:
                    stamp,event=screen.touches.pop(0);effect=panel.touch(event,stamp)
                    if effect is None:continue
                    record['physical_events'].append(dict(button=event.payload[1],effect=effect,signal=NAMES[panel.signal],seconds=panel.seconds,
                                                         utc=datetime.now(timezone.utc).isoformat(),elapsed_host_s=time.monotonic()-began,
                                                         origin=record['input_origin']))
                    generation+=1
                    if effect in ('select','duration','stop'):
                        if future:
                            cancel.set();status='STOPPING'
                            if job_cancel_reason!='stop':job_cancel_reason=effect
                        else:status='IDLE'
                    elif not fault and not future and effect in ('check','start'):
                        kind='check' if effect=='check' else 'run'
                        cancel=threading.Event();job_generation=generation
                        job_cancel_reason=None
                        future=pool.submit(job,kind,NAMES[panel.signal],panel.seconds,cancel,messages)
                        status='CHECKING' if kind=='check' else 'STARTING'
                    elif effect=='unapplied' and not future:status='APPLY'
                    if fault:status='FAULT'
                    screen.fields(panel.fields(status));save()
                while not messages.empty():
                    message=messages.get_nowait();log('backend',message=message)
                    if not fault and future and not cancel.is_set():
                        status='RUNNING';screen.fields(panel.fields(status))
                if future and future.done():
                    result=future.result();result['report_sha256']=control.sha(ROOT/result['report'])
                    result['cancel_reason']=job_cancel_reason
                    record['jobs'].append(result);future=None
                    if not result['passed']:fault=True;panel.applied=None;status='FAULT'
                    elif result['kind']=='check' and not cancel.is_set() and generation==job_generation:
                        panel.checked();status='READY'
                    else:panel.applied=None;status='IDLE'
                    screen.fields(panel.fields(status));save()
                if time.monotonic()-last_heartbeat>=.5:
                    screen.query('get t1.txt','text',status.encode('ascii'))
                    record['heartbeats']=record.get('heartbeats',0)+1;save();last_heartbeat=time.monotonic()
                completed={x.get('signal') for x in record['jobs'] if x.get('kind')=='run' and x.get('passed') and not x.get('cancelled')}
                stopped=any(x.get('kind')=='run' and x.get('passed') and x.get('cancelled') and not x.get('before_RF')
                            and x.get('cancel_reason')=='stop' for x in record['jobs'])
                if set(args.required_signals)<=completed and (not args.require_stop_test or stopped) and future is None:
                    record['required_presets_and_stop_completed']=True;break
            success_status='passed_P79_protocol_replay_RF_presets_and_cleanup' if driver else 'passed_P79_physical_screen_RF_presets_and_cleanup'
            record['status']=(success_status if record.get('required_presets_and_stop_completed')
                              else 'partial_P79_interactive_session') if not fault else 'failed_P79_interactive_session'
        except Exception as error:
            record.update(status='failed_or_unconfirmed_P79_interactive_session',error=repr(error))
        finally:
            cancel.set()
            # Remain in the turn while the exact owned bounded child is cleaned.
            if future:
                while not future.done():time.sleep(.1)
                result=future.result();result['report_sha256']=control.sha(ROOT/result['report'])
                result['cancel_reason']=job_cancel_reason or 'session_end'
                record['jobs'].append(result)
            if screen:
                try:screen.fields(panel.fields('FAULT' if fault or record['status'].startswith('failed') else 'OFFLINE'))
                except Exception as error:record['final_screen_error']=repr(error)
                screen.close()
            record['serial_closed']=True;save();print(record['status'],flush=True)
    return 0 if record['status'].startswith('passed_') else 1

if __name__=='__main__':raise SystemExit(main())
