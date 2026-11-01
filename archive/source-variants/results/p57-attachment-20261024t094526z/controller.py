"""Bounded, single-RX-context calibrated AI demo. No new model training.

Source truth is recorded here only; it is never passed to the receiver.
Startup selection must be paused first. All board writes below are RAM evidence,
bounded TX source operations, and ordinary RX; no PL or RF attribute writes.
"""
import argparse,json,re,time,uuid
import sys
sys.path.insert(0,'C:\\Users\\project_user\\Documents\\Codex\\2026-09-09\\2026-fpga-fmql30tai-fpai-python-c\\outputs\\rf-signal-lab\\experiments')
from datetime import datetime,timezone
from pathlib import Path
from p45_checkpoint import ROOT,read,write,sha,rel
from p46_console import Console
from p46_preflight import parse_names
from p35_once_merged_trial import AuditPort
from p35_uart_files import upload
from p36_full_rx_run import RF_EXPECTED,CRITICAL_KERNEL
from p46_known_source import GUARD_SHA
from p52_ram import board_ram_tmp


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--policy',required=True,type=Path)
    ap.add_argument('--long',action='store_true',help='630 s RX, twelve 45 s bounded TX cases; otherwise 85 s smoke')
    args=ap.parse_args();policy=read(args.policy);build=read(ROOT/policy['build'])
    if policy['status']!='passed_runtime_policy_19_steps_tone_fit_and_frozen_frontend_parity' or sha(ROOT/policy['build'])!=policy['build_sha256']:raise ValueError('policy gates required')
    for k,v in build['inputs_sha256'].items():
        if sha(ROOT/k)!=v:raise ValueError('build input changed '+k)
    binary=ROOT/build['binary']
    if sha(binary)!=build['binary_sha256']:raise ValueError('binary changed')
    source_path=ROOT/'results/p57-source-20261024T094437Z/report.json';sources=read(source_path)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=ROOT/'results'/('p57-live-'+stamp);out.mkdir()
    stage='/tmp/p35-p56-'+stamp[9:15];directory='/run/p42-000043/data'
    duration=900000;seconds=12;cycles=1
    if args.long:raise ValueError('attach trial has three bounded 12-second sources only')
    r=dict(status='preflight',stages=[],segments=[],samples=[],archives={},policy=rel(args.policy),policy_sha256=sha(args.policy),
        build=policy['build'],build_sha256=sha(ROOT/policy['build']),source_report=rel(source_path),source_sha256=sha(source_path),
        expected_boot=sources['RX_expected_boot'],TX_expected_boot=sources['expected_boot'],stage=stage,directory=directory,
        duration_ms=duration,seconds_per_TX=seconds,cycles=cycles,serial_closed=False,persistent_AI_default=False,
        RF_attribute_writes=False,PL_changes=False,TX_peak_component_counts=256,TX_gain_db=-10,
        acceptance_protocol=dict(known_signal_minimum_coverage=.70,known_signal_minimum_conditional_accuracy=.90,
            interval_start_after_sample_s=2,interval_end_margin_s=3,noise_and_pilot_must_abstain=True,
            calibration_must_be_same_boot=True,physical_LCD_confirmed=False),
        scope='deployment regression on exposed seed2315, not independent accuracy; no measured SNR, universal unknown detection or ADC continuity proof')
    rx=tx=None;tx_pending=None;pid=None;rx_running=False;shot=0
    r.update(startup_profile='p57',boot_report='results/p57-boot-20261024T094321Z/report.json',boot_report_sha256='ac4d559ab45b0facf676d2ec5e3431ec9990d45940eeabe648b86cfdf2e3281f',clock_readback='results/p36-clockwiz-readback-20261024T094437Z/report.json',clock_readback_sha256='c08dbb20abf3f49f76bb2e6bef125923b0ee494835493f386cb17dc2cfb5ba8d',host_launches_RX=False,calibration_uses_new_boot=True,persistent_AI_default=True)
    def save():write(out/'report.json',r)
    def digest(board,path):
        board.command('v='+path);found=re.findall(r'^([0-9a-f]{64})\s+\S+\r?$',board.command('sha256sum $v'),re.M)
        if len(found)!=1:raise ValueError('ambiguous hash')
        return found[0]
    def names(board):
        board.command('ir=/sys/bus/iio/devices')
        return parse_names(board.command('for n in $ir/iio:device*;do echo __D__$n:$(cat $n/name)__E__;done'))
    def one_json(command):
        rows=[json.loads(s) for s in rx.command(command).splitlines() if s.startswith('{')]
        if len(rows)!=1:raise ValueError('ambiguous native JSON')
        return rows[0]
    def sample():
        ai=one_json('cat $o/ai.json');r['samples'].append(ai);save();return ai
    def wait_for(predicate,limit):
        end=time.monotonic()+limit
        while time.monotonic()<end:
            a=sample()
            if predicate(a):return a
            time.sleep(.5)
        raise ValueError('runtime state deadline')
    def idle_rx():
        if rx.value('/proc/sys/kernel/random/boot_id')!=r['expected_boot'] or rx.value('/proc/sys/kernel/tainted')!='0':raise ValueError('RX boot/taint changed')
        n=names(rx);rx.command('cd '+n['ad9361-phy'])
        if {k:rx.value(k) for k in RF_EXPECTED}!=RF_EXPECTED:raise ValueError('RX RF differs')
        rx.command('cd '+n['cf-ad9361-lpc'])
        if rx.value('buffer/enable')!='0' or any(rx.value('scan_elements/in_voltage'+str(i)+'_en')!='0' for i in range(4)):raise ValueError('RX DMA not idle')
        if re.search(CRITICAL_KERNEL,rx.command('dmesg | tail -n 160')):raise ValueError('kernel error')
    def tx_idle():
        tx.command('cd '+sources['remote_directory']);inspection=tx.command('./guard --inspect',timeout=15)
        if any(not re.search(r'^dds'+str(i)+r'_raw=0(?:\.0+)?\r?$',inspection,re.M) for i in range(8)):raise ValueError('TX zero DDS source unconfirmed')
        if tx.value(txnames['cf-ad9361-dds-core-lpc']+'/buffer/enable')!='0':raise ValueError('TX DMA active')
        return inspection
    def start_tx(name,length):
        nonlocal tx_pending
        tx_idle();tx.command('cd '+sources['remote_directory'])
        if digest(tx,sources['remote_directory']+'/'+name)!=sources['files_sha256'][name]:raise ValueError('source changed')
        tx.command('p='+name);tx.command('h='+sources['files_sha256'][name]);tx.command('b=boot-session:'+r['TX_expected_boot'])
        tx.command('n=131072; f=30720000; l=2450000000; w=18000000')
        marker='__P56_TX_'+uuid.uuid4().hex[:8]+'__'
        case=dict(name=name,expected_class={'bpsk':0,'qpsk':1,'qam16':2}.get(name,-1),seconds=length,marker=marker,cleanup_verified=False)
        r['segments'].append(case);tx_pending=case;save()
        cmd='./guard --run $p $n $f $l $w -10 '+str(length)+' $b A $h RF_LINK_REVIEWED'
        if len(cmd)>72:raise ValueError('TX command too long')
        tx.port.write((cmd+"\rprintf '\\n"+marker+":%s\\n' \"$?\"\r").encode('ascii'))
        case['start_stdout']=tx.read(10,r'CYCLIC_PUSH_SUBMITTED samples=131072 deadline_seconds='+str(length))
        if 'CYCLIC_PUSH_SUBMITTED samples=131072 deadline_seconds='+str(length) not in case['start_stdout']:raise ValueError('bounded TX submission unconfirmed')
        case['host_submitted_monotonic']=time.monotonic();a=sample()
        case['receiver_elapsed_anchor']=a['elapsed_s'];case['score_start_s']=a['elapsed_s']+2;case['score_end_s']=a['elapsed_s']+length-3;save()
        return case
    def finish_tx():
        nonlocal tx_pending
        case=tx_pending;tail=tx.read(8,r'^'+case['marker']+r':\d+\r?$');case['end_stdout']=tail
        if not re.search(r'^'+case['marker']+r':0\r?$',tail,re.M) or 'TX_CLEANUP buffer_released=true rf_settings_written=false status=0' not in tail or 'DDS_ZERO_SOURCE_READBACK=PASS' not in tail:raise ValueError('bounded TX cleanup unconfirmed')
        case['after_inspect']=tx_idle();case['cleanup_verified']=True;tx_pending=None;save()
    def request_shot():
        nonlocal shot
        shot+=1;rx.command('echo '+str(shot)+' >$h');time.sleep(.8)
        return shot
    def archive_file(name,key):
        rx.command('v='+directory+'/'+name)
        raw_sha=digest(rx,directory+'/'+name);rx.command('z='+stage+'/'+key+'.gz')
        rx.command('gzip -1 -c $v >$z',timeout=20);rx.command('gzip -t $z')
        compressed_sha=digest(rx,stage+'/'+key+'.gz')
        def count(path):
            rx.command('v='+path);rows=re.findall(r'^__N__(\d+)__E__\r?$',rx.command('echo __N__$(wc -c <$v)__E__'),re.M)
            if len(rows)!=1:raise ValueError('archive size ambiguous')
            return int(rows[0])
        r['archives'][key]=dict(remote=stage+'/'+key+'.gz',expected_bytes=count(stage+'/'+key+'.gz'),expected_sha256=compressed_sha,
            raw_bytes=count(directory+'/'+name),raw_sha256=raw_sha,original_name=name);save()
    save();(out/'executed.py').write_bytes(Path(__file__).read_bytes());print(out,flush=True)
    try:
        for port in ('COM9','COM8'):
            b=Console(port,r,save);folder=out/port;folder.mkdir();b.port=AuditPort(b.port,folder)
            if port=='COM9':tx=b
            else:rx=b
            b.shell();b.command('p56_prompt=$PS1');b.command("PS1=''");b.command('stty -echo')
        if rx.value('/proc/sys/kernel/random/boot_id')!=r['expected_boot'] or rx.value('/proc/sys/kernel/tainted')!='0':raise ValueError('RX identity changed')
        if digest(rx,'/etc/rcS.d/S99board')!='e3c75e72a457262fef44939fda1343b5df25abd3dbfd03a95c885b067bb95a0b':raise ValueError('P57 startup selection changed')
        if digest(rx,'/etc/p43-20261024T093110Z/control')!='c1d81b5bc1677e0f521f64420e75a533a76a088fd9e25cd689c6a2ea67453d38':raise ValueError('owned control changed')
        if tx.value('/proc/sys/kernel/random/boot_id')!=r['TX_expected_boot'] or tx.value('/proc/sys/kernel/tainted')!='0' or 'Linux pzp201' not in tx.command('uname -a'):raise ValueError('TX identity differs')
        txnames=names(tx)
        if digest(tx,sources['remote_directory']+'/guard')!=GUARD_SHA:raise ValueError('guard changed')
        r['initial_TX_inspection']=tx_idle();r['resolved_RAM_tmp']=board_ram_tmp(rx);save()
        rx.command('mkdir '+stage);rx.command('s='+stage)
        rx.command('j='+'/etc/p43-20261024T093110Z')
        rx.command('o=/run/p42-000043/data');rx.command('h=/run/p42-000043/shot')
        rx.command('test ! -e /run/p42-000043/exit')
        pid=int(rx.value('/run/p42-000043/pid'));r['owned_timeout_pid']=pid;rx_running=True
        r['status']='attached_to_board_started_RX_waiting_calibration';save()
        first=wait_for(lambda a:a['state']=='CALIBRATION_REQUIRED',8);request_shot()
        token=uuid.uuid4().hex;r['calibration_token']=token
        rx.command('k='+token);rx.command('sh $j/control calibrate $k')
        wait_for(lambda a:a['state']=='WAIT_PILOT',8)
        case=start_tx('tone',15);wait_for(lambda a:a['ready'] and a['state']=='UNSUPPORTED_TONE',8);request_shot()
        while time.monotonic()-case['host_submitted_monotonic']<15:time.sleep(.5)
        finish_tx();wait_for(lambda a:a['state']=='NO_USABLE_SIGNAL',8);request_shot()
        r['status']='RX_running_calibrated';save()
        for cycle in range(cycles):
            for name in ('bpsk','qpsk','qam16'):
                case=start_tx(name,seconds);shot_requested=False
                print('P56 controlled source '+name+' cycle '+str(cycle+1),flush=True)
                while time.monotonic()-case['host_submitted_monotonic']<seconds:
                    a=sample();since=time.monotonic()-case['host_submitted_monotonic']
                    if cycle==0 and since>=5 and not shot_requested:case['shot']=request_shot();shot_requested=True
                    time.sleep(min(4,max(.05,seconds-since)))
                finish_tx();wait_for(lambda a:a['state']=='NO_USABLE_SIGNAL',8)
        r['status']='final_source_off_six_second_hold';save()
        held=time.monotonic()
        while time.monotonic()-held<6:
            sample();time.sleep(.5)
        r['status']='known_cases_complete_owned_stop';save()
        rx.command('sh $j/control stop',timeout=12);rx_running=False
        wait_for(lambda a:a['state']=='STOPPED',5)
        r['launcher_exit']=rx.value('/run/p42-000043/exit')
        if r['launcher_exit'] not in ('0','143'):raise ValueError('owned RX completion unconfirmed')
        r['native_summary']=one_json('cat $o/summary.json');r['final_AI']=one_json('cat $o/ai.json')
        s=r['native_summary']
        if s['status']!='stopped' or s['reason']!='signal_requested_stop' or s['display_revision']!='p56' or not s['buffer_released'] or not s['context_released'] or not s['worker_joined'] or not s['RF_after_matches'] or s['cleanup_unconfirmed']:raise ValueError('native lifecycle failed')
        idle_rx();r['final_TX_inspection']=tx_idle();r['board_native_capture_complete']=True;save()
        archive_file('ai-history.jsonl','history');archive_file('fb.raw','final-fb')
        for id in range(1,shot+1):
            for ext in ('json','bin','raw'):archive_file('shot-'+format(id,'02d')+'.'+ext,'shot'+str(id)+'-'+ext)
        r.update(status='captured_runtime_AI_pending_byte_archives_and_independent_review',RX_idle_verified=True,TX_idle_verified=True)
    except Exception as e:r.update(status='failed_or_unconfirmed_runtime_AI',error=repr(e));save()
    finally:
        if tx and tx_pending:
            try:
                remaining=max(0,tx_pending['seconds']-(time.monotonic()-tx_pending.get('host_submitted_monotonic',time.monotonic())))
                if remaining>0:time.sleep(min(remaining+1,60))
                finish_tx()
            except Exception as e:r['TX_cleanup_error']=repr(e)
        if rx and rx_running and pid:
            try:
                rx.command('sh $j/control stop',timeout=12)
                idle_rx();r['error_stop_RX_idle_verified']=True
            except Exception as e:r['RX_cleanup_error']=repr(e)
        for b in (rx,tx):
            if b:
                try:b.command('stty echo');b.command('PS1=$p56_prompt')
                except Exception as e:r['TTY_restore_error']=repr(e)
                b.close()
        r['serial_closed']=True;save()
    print(out);print(r['status']);return int(not r['status'].startswith('captured_'))
if __name__=='__main__':raise SystemExit(main())
