"""Bounded peak-256 RF sources and complete RX1 DMA snapshots; no RF setting writes."""
import argparse,hashlib,json,re,time
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
from p32_session import ROOT
from p46_console import Console
from p46_preflight import parse_names
from p35_once_merged_trial import AuditPort
from p36_full_rx_run import RF_EXPECTED,load_build,validate_completion,validate_metadata,json_rows,CRITICAL_KERNEL

NAMES=('tone','bpsk','qpsk','qam16')
GUARD_SHA='0a188e1e1c0c19a165231c1d5589ff5d72adbf284d98d2bdf39cfc6a65b1163b'
def sha(b):return hashlib.sha256(b).hexdigest()
def read(p):return json.loads(p.read_text('utf-8'))

def source_bytes_valid(raw):
    if len(raw)!=131072*4:raise ValueError('source byte count')
    x=np.frombuffer(raw,dtype='<i2')
    if np.any(x&15) or int(np.max(abs(x.astype(np.int32))))>4096:raise ValueError('source exceeds reviewed peak256 or packing')
    return True

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan',type=Path,required=True);p.add_argument('--source-report',type=Path,required=True);p.add_argument('--rx-smoke',type=Path,required=True)
    p.add_argument('--case',action='append',choices=NAMES);p.add_argument('--blocks',type=int,default=4,choices=range(1,9))
    args=p.parse_args();sources=read(args.source_report);smoke=read(args.rx_smoke);cases=args.case or list(NAMES)
    if len(set(cases))!=len(cases):raise ValueError('duplicate case')
    if sources['status']!='guard_and_peak256_sources_restored_inspected_checked_no_TX' or not sources['serial_closed'] or sources['files_sha256']['guard']!=GUARD_SHA:raise ValueError('checked source restore required')
    origin=Path(sources['source_report'])
    plan=read(args.plan);package=read(origin)
    if plan['status']!='frozen_before_new_RF_acquisition' or args.blocks!=plan['blocks_per_case']:raise ValueError('frozen capture plan required')
    groups=[g for g in plan['groups'] if g['seed']==package.get('seed')]
    if len(groups)!=1 or sha(origin.read_bytes())!=groups[0]['package_sha256'] or cases!=groups[0]['case_order']:raise ValueError('planned seed/source/order mismatch')
    if sha(origin.read_bytes())!=sources['source_report_sha256']:raise ValueError('source origin changed')
    for name in NAMES:
        raw=(origin.parent/name).read_bytes();source_bytes_valid(raw)
        if sha(raw)!=sources['files_sha256'][name]:raise ValueError('host source changed')
    if smoke['status']!='passed_finite_full_returned_buffers_board_only_pending_host_retrieval' or not smoke['independent_final_idle_verified'] or smoke['expected_boot']!=sources['RX_expected_boot']:raise ValueError('new receiver smoke required')
    build=load_build(Path(smoke['build_report']))
    if smoke['binary_sha256']!=build['report']['binary_sha256']:raise ValueError('receiver build mismatch')
    if not plan['physical_link']['old_TX1_to_new_RX1A_same_connection_confirmed']:raise ValueError('RF connection not confirmed')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=ROOT/'results'/('p52-known-'+stamp);out.mkdir(exist_ok=False)
    r=dict(status='preflight',stages=[],cases=[],source_report=str(args.source_report.resolve()),source_report_sha256=sha(args.source_report.read_bytes()),
        rx_smoke=str(args.rx_smoke.resolve()),rx_smoke_sha256=sha(args.rx_smoke.read_bytes()),TX_expected_boot=sources['expected_boot'],expected_boot=sources['RX_expected_boot'],
        RF_attribute_writes=False,PL_changes=False,TX_duration_limit_s=15,source_peak_component_counts=256,
        plan=str(args.plan.resolve()),plan_sha256=sha(args.plan.read_bytes()),seed=package['seed'],split=groups[0]['role'],capture_session=groups[0]['planned_capture_session'],lossless_proven=False,known_source_diagnostic_only=True,physical_RF_silence_measured=False,serial_closed=False)
    (out/'executed.py').write_bytes(Path(__file__).read_bytes())
    def save():(out/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    tx=rx=None;tx_shell=rx_shell=False;active=None;save()
    def digest(b,path):
        b.command('v='+path);v=re.findall(r'^([0-9a-f]{64})\s+\S+\r?$',b.command('sha256sum $v'),re.M)
        if len(v)!=1:raise ValueError('ambiguous hash')
        return v[0]
    def device_names(b):
        b.command('ir=/sys/bus/iio/devices');return parse_names(b.command('for n in $ir/iio:device*;do echo __D__$n:$(cat $n/name)__E__;done'))
    def rx_idle():
        if rx.value('/proc/sys/kernel/random/boot_id')!=r['expected_boot'] or rx.value('/proc/sys/kernel/tainted')!='0':raise ValueError('RX identity changed')
        names=device_names(rx);rx.command('cd '+names['cf-ad9361-lpc'])
        if rx.value('buffer/enable')!='0' or any(rx.value('scan_elements/in_voltage'+str(i)+'_en')!='0' for i in range(4)):raise ValueError('RX not released')
        rx.command('cd '+names['ad9361-phy'])
        if {k:rx.value(k) for k in RF_EXPECTED}!=RF_EXPECTED:raise ValueError('RX RF differs')
        if re.search(CRITICAL_KERNEL,rx.command('dmesg | tail -n 100')):raise ValueError('kernel fault')
    try:
        for port in ('COM9','COM8'):
            b=Console(port,r,save);b.shell();folder=out/port;folder.mkdir();b.port=AuditPort(b.port,folder)
            if port=='COM9':tx=b;tx_shell=True
            else:rx=b;rx_shell=True
            # Echo-off output must not share a line with the interactive prompt.
            b.command('p46_saved_prompt=$PS1');b.command("PS1=''")
            b.command('stty -echo')
        if 'Linux pzp201' not in tx.command('uname -a') or tx.value('/proc/sys/kernel/random/boot_id')!=r['TX_expected_boot'] or tx.value('/proc/sys/kernel/tainted')!='0':raise ValueError('TX identity differs')
        if 'Zynq-Tronlong' not in rx.command('uname -a'):raise ValueError('RX identity differs')
        if re.search('guard --run|arm-tx-source',tx.command('ps')) or re.search(r'/run/p42-\d+/monitor|iio_readdev',rx.command('ps -ef')):raise ValueError('experiment active')
        if digest(tx,sources['remote_directory']+'/guard')!=GUARD_SHA or digest(rx,smoke['remote_binary'])!=smoke['binary_sha256']:raise ValueError('executable changed')
        if digest(rx,'/etc/rcS.d/S99board')!=sha((ROOT/'board/boot/S99board').read_bytes()):raise ValueError('archive startup selection not paused')
        txnames=device_names(tx)
        for device in ('cf-ad9361-lpc','cf-ad9361-dds-core-lpc'):
            if tx.value(txnames[device]+'/buffer/enable')!='0':raise ValueError('TX-side DMA active')
        rx_idle();r['status']='capturing_bounded_known_sources';save()
        for name in cases:
            case=dict(name=name,blocks=args.blocks,TX_started_maybe=False,TX_cleanup_verified=False);r['cases'].append(case);active=case;save()
            rx_idle();tx.command('cd '+sources['remote_directory'])
            if digest(tx,sources['remote_directory']+'/'+name)!=sources['files_sha256'][name]:raise ValueError('board source changed')
            tx.command('p='+name);tx.command('h='+sources['files_sha256'][name]);tx.command('b=boot-session:'+r['TX_expected_boot'])
            tx.command('n=131072; f=30720000; l=2450000000; w=18000000')
            marker='__P46_TX_'+name+'__';case['exit_marker']=marker
            command='./guard --run $p $n $f $l $w -10 15 $b A $h RF_LINK_REVIEWED'
            case['TX_started_maybe']=True;tx_shell=False;save()
            tx.port.write((command+"\rprintf '\\n"+marker+":%s\\n' \"$?\"\r").encode('ascii'))
            submitted_host=time.monotonic();start=tx.read(10,r'CYCLIC_PUSH_SUBMITTED samples=131072 deadline_seconds=15');case['TX_start']=start;save()
            if 'CYCLIC_PUSH_SUBMITTED samples=131072 deadline_seconds=15' not in start:raise ValueError('TX did not confirm bounded submission')
            print('Known source '+name+' submitted; retaining '+str(args.blocks)+' complete RX1 buffers',flush=True)
            directory='/tmp/p36-full-'+stamp[9:15]+'-'+name;case['output_directory']=directory
            rx.command('a='+smoke['remote_binary']);rx.command('o='+directory);rx.command('test ! -e $o')
            rx_shell=False
            try:result=rx.command('timeout -k 2 28 $a $o '+str(args.blocks),timeout=40);rx_shell=True
            except Exception:
                if r['stages'] and isinstance(r['stages'][-1].get('exit_code'),int):rx_shell=True
                raise
            case['native_start'],case['native_completion']=validate_completion(result,args.blocks)
            case['host_capture_completed_after_submission_s']=time.monotonic()-submitted_host
            if case['host_capture_completed_after_submission_s']>=14:raise ValueError('capture not conservatively inside 15-second TX window')
            rows=json_rows(rx.command('cat $o/metadata.json'))
            if len(rows)!=1:raise ValueError('metadata ambiguous')
            case['native_metadata']=validate_metadata(rows[0],args.blocks);rx_idle()
            raw=directory+'/iq-packed.bin';case['raw_sha256']=digest(rx,raw);case['raw_bytes']=args.blocks*262144
            rx.command('o='+directory);rx.command('r=$o/iq-packed.bin');rx.command('z=$r.gz')
            rx.command('timeout -k 2 28 gzip -1 -c $r >$z',timeout=40);rx.command('gzip -t $z')
            case.update(remote=raw+'.gz',compressed_sha256=digest(rx,raw+'.gz'))
            size=re.findall(r'^__N__(\d+)__E__\r?$',rx.command('echo __N__$(wc -c <$z)__E__'),re.M)
            if len(size)!=1:raise ValueError('archive size ambiguous')
            case['compressed_bytes']=int(size[0]);save()
            end=tx.read(42,r'^'+marker+r':\d+\r?$');case['TX_end']=end
            if not re.search(r'^'+marker+r':0\r?$',end,re.M) or 'TX_CLEANUP buffer_released=true rf_settings_written=false status=0' not in end or 'DDS_ZERO_SOURCE_READBACK=PASS' not in end:raise ValueError('TX completion not verified')
            tx_shell=True
            if tx.value(txnames['cf-ad9361-dds-core-lpc']+'/buffer/enable')!='0':raise ValueError('TX buffer remains enabled')
            tx.command('cd '+sources['remote_directory']);inspection=tx.command('./guard --inspect',timeout=15);case['TX_after']=inspection
            for i in range(8):
                if not re.search(r'^dds'+str(i)+r'_raw=0(?:\.0+)?\r?$',inspection,re.M):raise ValueError('DDS zero source not retained')
            case.update(TX_cleanup_verified=True,status='captured_and_cleaned_up_pending_host_archive');active=None;save()
            print('Known source '+name+' completed; native TX cleanup and RX release verified',flush=True)
        rx_idle();r.update(status='passed_bounded_known_source_captures_pending_host_archive',independent_final_RX_idle=True,all_TX_cleanup_verified=True)
    except Exception as e:
        r.update(status='failed_or_unconfirmed',error=repr(e));save()
        if tx and active and active['TX_started_maybe'] and not tx_shell:
            try:
                marker=active['exit_marker'];tail=tx.read(42,r'^'+marker+r':\d+\r?$');active['TX_error_cleanup']=tail
                tx_shell=bool(re.search(r'^'+marker+r':\d+\r?$',tail,re.M))
            except Exception as err:r['TX_error_cleanup_exception']=repr(err)
    finally:
        for b,shell in ((tx,tx_shell),(rx,rx_shell)):
            if b:
                if shell:
                    try:b.command('stty echo');b.command('PS1=$p46_saved_prompt')
                    except Exception as e:r['TTY_restore_error']=repr(e)
                b.close()
        r.update(serial_closed=True,TX_shell_confirmed=tx_shell,RX_shell_confirmed=rx_shell);save();print(out);print(r['status'])
    return 0 if r['status'].startswith('passed_') else 1
if __name__=='__main__':raise SystemExit(main())
