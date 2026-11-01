"""Bounded RAM-only P67 receive/display trial. No RF transmission or boot edits."""
import argparse,importlib.util,io,json,re,tarfile,time
from datetime import datetime,timezone
from pathlib import Path
from p45_checkpoint import ROOT,read,write,sha,rel
from p35_uart_files import upload
from p52_ram import board_ram_tmp
from p26_retrieve_chunks import decode_payload
from p36_retrieve_file import CHUNK_BYTES,chunk_command,unpack_verified,validate_sizes

spec=importlib.util.spec_from_file_location('control',ROOT/'host/board_control.py')
control=importlib.util.module_from_spec(spec);spec.loader.exec_module(control)
from rfsig.board_session import require_rx_control,require_tx_off,one_json

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--build',required=True,type=Path)
    ap.add_argument('--review',required=True,type=Path);a=ap.parse_args()
    build=read(a.build);review=read(a.review)
    if (build['status']!='passed_P67_build_12_lifecycle_cases_not_deployed'
        or review['status']!='passed_P67_8_renderer_numeric_tests_19_policy_steps'
        or review['build_sha256']!=sha(a.build)):raise ValueError('reviewed candidate required')
    for p,h in build['inputs_sha256'].items():
        if sha(ROOT/p)!=h:raise ValueError('build input changed '+p)
    binary=ROOT/build['binary']
    if sha(binary)!=build['binary_sha256']:raise ValueError('binary changed')
    with control.operation_lock():
        c=control.Controller('p67-dashboard-trial');print(c.out,flush=True)
        c.record.update(build=rel(a.build),build_sha256=sha(a.build),offline_review=rel(a.review),
            offline_review_sha256=sha(a.review),candidate_RF_transmissions=0,
            duration_ms=120000,stages=c.record['stages'],candidate_started=False,chunks=[])
        running=False;pid=None
        try:
            c.status();tx=c.record['boards']['TX'];rx=c.record['boards']['RX']
            require_tx_off(tx);require_rx_control(rx,running=False)
            c.record['initial_RX']=rx;c.record['initial_TX']=tx;c.save()
            with c.board('RX') as (b,identity):
                fresh=c.inspect('RX',b,identity);require_rx_control(fresh,running=False)
                if fresh['boot_id']!=rx['boot_id']:raise ValueError('RX rebooted')
                c.record['RAM_tmp']=board_ram_tmp(b)
                stage='/tmp/p35-p67-'+datetime.now(timezone.utc).strftime('%H%M%S')
                c.record['stage']=stage;c.record['data_directory']=stage+'/data';c.save()
                b.command('s='+stage);b.command('test ! -e $s');b.command('mkdir $s')
                b.command("PS1='# '")
                upload(b,stage+'/a',binary.read_bytes())
                b.command("PS1=''");b.command('stty -echo')
                if c.digest(b,stage+'/a')!=build['binary_sha256']:raise ValueError('upload digest mismatch')
                b.command('chmod 755 $s/a');b.command('o=$s/data')
                b.command('export P56_CONTROL_FILE=$s/control P56_SHOT_FILE=$s/shot')
                b.command('test ! -e $s/control')
                b.command('timeout -k 2 150 $s/a $o 120000 500 >$s/log 2>&1 &')
                b.command('pid=$!; echo $pid >$s/pid');pid=int(b.value(stage+'/pid'))
                c.record.update(owned_timeout_pid=pid,candidate_started=True,status='P67_RX_starting');running=True;c.save()
                begin=time.monotonic();snapshots=[]
                while time.monotonic()-begin<145:
                    d=one_json(c.optional(b,stage+'/data/dashboard.json'),optional=True)
                    if d:
                        snapshots.append(d);c.record['samples']=snapshots;c.record['status']='P67_RX_'+d['state'];c.save()
                        print('P67 '+d['state']+' source='+str(d['source_block_sequence'])+' elapsed='+str(round(d['elapsed_software_s'])),flush=True)
                        if d['state'] in ('finished','stopped','failed'):break
                    time.sleep(5)
                else:raise TimeoutError('candidate duration exceeded')
                b.command('wait $pid',timeout=10);running=False
                summary=one_json(c.optional(b,stage+'/data/summary.json'))
                ai=one_json(c.optional(b,stage+'/data/ai.json'))
                dash=one_json(c.optional(b,stage+'/data/dashboard.json'))
                c.record.update(native_summary=summary,final_AI=ai,final_dashboard=dash)
                if (summary['status']!='pass' or summary['reason']!='duration_complete'
                    or summary['display_revision']!='p67' or not summary['buffer_released']
                    or not summary['context_released'] or not summary['worker_joined']
                    or not summary['RF_after_matches'] or summary['cleanup_unconfirmed']
                    or ai['state']!='STOPPED' or dash['AI_state']!='STOPPED'
                    or dash['source_block_sequence']!=summary['last_display_sequence']):
                    raise ValueError('candidate lifecycle/evidence gate failed')
                fresh=c.inspect('RX',b,identity);require_rx_control(fresh,running=False)
                if fresh['boot_id']!=rx['boot_id'] or fresh['profile_hashes']!=rx['profile_hashes']:
                    raise ValueError('boot/persistent baseline changed')
                c.record['after_RX']=fresh;c.save()
                names=('dashboard.json','ai.json','ai-history.jsonl','progress.json','summary.json','last-display-packed.bin','fb.raw')
                b.command("f='dashboard.json ai.json ai-history.jsonl'")
                b.command('f="$f progress.json summary.json last-display-packed.bin fb.raw"')
                b.command('tar -cf $s/e.tar -C $o $f',timeout=20)
                b.command('gzip -1 -c $s/e.tar >$s/e.gz',timeout=20);b.command('gzip -t $s/e.gz')
                def count(path):
                    b.command('v='+path)
                    values=re.findall(r'^__N__(\d+)__E__\r?$',b.command('echo __N__$(wc -c <$v)__E__'),re.M)
                    if len(values)!=1:raise ValueError('ambiguous byte size')
                    return int(values[0])
                size,raw_size=count(stage+'/e.gz'),count(stage+'/e.tar');validate_sizes(size,raw_size)
                wanted,raw_wanted=c.digest(b,stage+'/e.gz'),c.digest(b,stage+'/e.tar')
                c.record['contract']=dict(remote=stage+'/e.gz',bytes=size,sha256=wanted,raw_bytes=raw_size,raw_sha256=raw_wanted);c.save()
                b.command('src='+stage+'/e.gz');pieces=[]
                for index,start in enumerate(range(0,size,CHUNK_BYTES)):
                    expected=min(CHUNK_BYTES,size-start)
                    h=re.findall(r'^([0-9a-f]{64})\s+-\r?$',b.command(chunk_command(index,'sha256sum'),timeout=20),re.M)
                    if len(h)!=1:raise ValueError('chunk hash ambiguous')
                    data=None
                    for attempt in range(3):
                        try:
                            candidate=decode_payload(b.command(chunk_command(index,'base64'),timeout=20),expected)
                            import hashlib
                            if hashlib.sha256(candidate).hexdigest()!=h[0]:raise ValueError('chunk hash mismatch')
                            data=candidate;break
                        except ValueError as e:
                            c.record.setdefault('transfer_retries',[]).append(dict(index=index,attempt=attempt,error=repr(e)))
                    if data is None:raise ValueError('chunk retries exhausted')
                    pieces.append(data);c.record['chunks'].append(dict(index=index,bytes=len(data),sha256=h[0],verified=True));c.save()
                packed=b''.join(pieces);raw=unpack_verified(packed,size,wanted,raw_size,raw_wanted)
                (c.out/'evidence.tar.gz').write_bytes(packed);files=c.out/'files';files.mkdir()
                with tarfile.open(fileobj=io.BytesIO(raw),mode='r:') as tf:
                    members=tf.getmembers()
                    if len(members)!=len(names) or {m.name for m in members}!=set(names) or not all(m.isfile() for m in members):raise ValueError('unexpected tar members')
                    for m in members:(files/m.name).write_bytes(tf.extractfile(m).read())
                if c.digest(b,stage+'/e.gz')!=wanted:raise ValueError('archive changed')
                c.record['files_sha256']={name:sha(files/name) for name in names}
            with c.board('TX') as (b,identity):
                ending=c.inspect('TX',b,identity);require_tx_off(ending)
                if ending['boot_id']!=tx['boot_id']:raise ValueError('TX rebooted')
                c.record['after_TX']=ending
            c.record.update(status='passed_P67_RAM_RX_dashboard_120s_byte_archived_pending_review',
                RX_stopped=True,TX_stopped=True,persistent_profile_changed=False,physical_visibility='pending_user_confirmation')
        except Exception as e:
            c.record.update(status='failed_or_unconfirmed_P67_trial',error=repr(e));c.save()
            if running and pid:
                try:
                    with c.board('RX') as (b,identity):
                        if b.value('/proc/sys/kernel/random/boot_id')!=rx['boot_id']:raise ValueError('boot changed')
                        cmd=b.command('tr "\\000" " " </proc/'+str(pid)+'/cmdline')
                        if stage+'/a' not in cmd:raise ValueError('owned command differs')
                        b.command('kill -TERM '+str(pid));time.sleep(4)
                        c.record['error_cleanup_RX']=c.inspect('RX',b,identity)
                except Exception as cleanup:c.record['cleanup_error']=repr(cleanup)
        c.record['serial_closed']=True;c.save();print(c.record['status'],flush=True)
        return int(not c.record['status'].startswith('passed'))
if __name__=='__main__':raise SystemExit(main())
