"""Run frozen real-RF C inference on ARM using hash-checked retained DMA files.

No RF acquisition, configuration, PL, persistent-file or framebuffer writes.
Only a small executable and one DMA scratch file are created in unique /tmp RAM.
"""
import argparse,json,re
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
from p45_checkpoint import ROOT,read,write,sha,rel
from p46_console import Console
from p35_once_merged_trial import AuditPort
from p35_uart_files import upload
from p36_full_rx_run import RF_EXPECTED,CRITICAL_KERNEL
from p52_ram import board_ram_tmp


def parse_inference(text,expected):
    rows=[];bench=[]
    for line in text.splitlines():
        if re.fullmatch(r'[012],[-+0-9.eE]+,[-+0-9.eE]+,[-+0-9.eE]+,[012]',line):
            rows.append(np.fromstring(line,sep=','))
        elif line.startswith('{'):bench.append(json.loads(line))
    a=np.asarray(rows)
    if a.shape!=(3,5) or not np.isfinite(a).all() or not np.array_equal(a[:,0],[0,1,2]):
        raise ValueError('missing, duplicate or malformed ARM inference rows')
    ref=np.asarray(expected)
    np.testing.assert_allclose(a[:,1:4],ref,rtol=1e-4,atol=5e-4)
    if not np.array_equal(a[:,4].astype(int),np.argmax(ref,axis=1)):
        raise ValueError('ARM/Python classes differ')
    return a,bench


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--evaluation',required=True,type=Path);args=p.parse_args()
    ev=read(args.evaluation);frozen_path=ROOT/ev['frozen'];frozen=read(frozen_path)
    if (ev['status']!='passed_independent_controlled_REAL_RF_classification_and_host_C_parity'
        or ev['frozen_sha256']!=sha(frozen_path) or len(ev['fixtures'])!=18):
        raise ValueError('passed frozen independent RF evaluation required')
    for v in frozen['frozen_inputs'].values():
        if sha(ROOT/v['path'])!=v['sha256']:raise ValueError('frozen input changed')
    batch_path=ROOT/ev['test_batch'];batch=read(batch_path)
    if sha(batch_path)!=ev['test_batch_sha256']:raise ValueError('test batch changed')
    arm=ROOT/frozen['frozen_inputs']['ARM']['path']
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p52-ARM-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    (out/'executed.py').write_bytes(Path(__file__).read_bytes())
    remote='/tmp/p35-ai-'+out.name[-7:-1]
    r=dict(status='preflight',stages=[],evaluation=rel(args.evaluation),evaluation_sha256=sha(args.evaluation),
        frozen=rel(frozen_path),frozen_sha256=sha(frozen_path),ARM_binary_sha256=sha(arm),
        expected_boot=batch['expected_boot'],checks=[],benchmarks=[],serial_closed=False,
        RF_operations=False,PL_changes=False,persistent_files_written=False,live_AI_on_LCD=False,
        scope='ARM execution on previously captured independent real RF, not continuous live stream')
    r.update(deployment_driver_revision='p55_tty_upload_fix',frozen_original_verifier='experiments/p52_arm_verify.py',frozen_original_verifier_sha256='45e1fb3c516e8e16098b53a5dcd0b8e915dc5275f41791ed42c06e0705f4639a',model_or_preprocessor_modified=False,fix='nonempty prompt only during existing upload protocol; empty prompt for framed numeric output')
    def save():write(out/'report.json',r)
    board=None;prompt_saved=False
    def digest(path):
        board.command('s='+path)
        values=re.findall(r'^([0-9a-f]{64})\s+\S+\r?$',board.command('sha256sum $s'),re.M)
        if len(values)!=1:raise ValueError('ambiguous board SHA')
        return values[0]
    def inspect(label):
        if ('Zynq-Tronlong' not in board.command('uname -a')
            or board.value('/proc/sys/kernel/random/boot_id')!=r['expected_boot']
            or board.value('/proc/sys/kernel/tainted')!='0'):raise ValueError('receiver identity/boot/taint')
        if digest('/etc/rcS.d/S99board')!=sha(ROOT/'board/boot/S99board'):raise ValueError('original paused startup guard required')
        if re.search(r'arm[-_]rx|arm[-_]panel|arm-latest|arm-tx-source|iio_readdev|/run/p42-\d+/monitor',board.command('ps -ef')):
            raise ValueError('competing receiver process')
        board.command('/etc/rcS.d/S99board --check-rf')
        board.command('ir=/sys/bus/iio/devices')
        text=board.command('for n in $ir/iio:device*;do echo __D__$n:$(cat $n/name)__E__;done')
        pairs=re.findall(r'^__D__(/sys/bus/iio/devices/iio:device\d+):([^\r\n]+)__E__\r?$',text,re.M)
        names={n:path for path,n in pairs}
        if any(sum(n==name for _,n in pairs)!=1 for name in ('ad9361-phy','cf-ad9361-lpc','cf-ad9361-dds-core-lpc')):
            raise ValueError('missing or duplicate RF device')
        board.command('cd '+names['ad9361-phy'])
        attrs={key:board.value(key) for key in RF_EXPECTED}
        if attrs!=RF_EXPECTED:raise ValueError('fixed RF configuration changed')
        board.command('cd '+names['cf-ad9361-lpc'])
        buffer=board.value('buffer/enable');scans=[board.value('scan_elements/in_voltage'+str(i)+'_en') for i in range(4)]
        if buffer!='0' or scans!=['0']*4:raise ValueError('DMA not idle')
        if re.search(CRITICAL_KERNEL,board.command('dmesg | tail -n 160')):raise ValueError('kernel error')
        r[label]=dict(boot=r['expected_boot'],taint='0',attributes=attrs,buffer=buffer,scans=scans);save()
    save()
    try:
        board=Console('COM8',r,save);board.port=AuditPort(board.port,out);board.shell()
        board.command('p52_prompt=$PS1');prompt_saved=True;board.command("PS1=''");board.command('stty -echo')
        inspect('before')
        r['resolved_RAM_tmp']=board_ram_tmp(board);save()
        board.command('mkdir '+remote)
        board.command("PS1='# '")
        upload(board,remote+'/a',arm.read_bytes())
        board.command("PS1=''");board.command('stty -echo')
        board.command('chmod 755 '+remote+'/a');board.command('b='+remote+'/a');board.command('x='+remote+'/x')
        r['status']='running_frozen_ARM_inference';save();verified_files={}
        for fixture in ev['fixtures']:
            group=next(g for g in batch['groups'] if g['seed']==fixture['seed'])
            trial=read(ROOT/group['trial'])
            if sha(ROOT/group['trial'])!=group['trial_sha256']:raise ValueError('trial changed')
            case=next(c for c in trial['cases'] if c['name']==fixture['source_name'])
            src=case['remote'].removesuffix('.gz')
            if not re.fullmatch(r'/tmp/p36-full-\d{6}-(?:bpsk|qpsk|qam16)/iq-packed.bin',src):raise ValueError('unexpected retained raw path')
            if src not in verified_files:
                if digest(src)!=case['raw_sha256']:raise ValueError('retained complete DMA file changed')
                verified_files[src]=case['raw_sha256']
            board.command('s='+src)
            board.command('dd if=$s of=$x bs=262144 skip='+str(fixture['block'])+' count=1')
            if digest(remote+'/x')!=fixture['sha256']:raise ValueError('ARM fixture differs from evaluated test')
            board.command('f='+format(fixture['common_IF_hz'],'.17g'))
            for mode in ('fp32','int8'):
                bench=fixture['block']==0 and fixture['seed']==ev['fixtures'][0]['seed'] and mode==ev['selected_mode']
                text=board.command('timeout -k 2 12 $b $x $f '+mode+(' --bench' if bench else ''),timeout=16)
                a,b=parse_inference(text,fixture['expected_'+mode])
                if bench:
                    if len(b)!=1 or b[0]['repeats']!=10 or b[0]['frames_per_block']!=3 or not 0<b[0]['mean_block_ms']<=b[0]['max_block_ms']<1000:
                        raise ValueError('invalid or excessive ARM benchmark')
                    r['benchmarks'].append(dict(source=fixture['source_name'],mode=mode,**b[0]))
                elif b:raise ValueError('unexpected benchmark')
                r['checks'].append(dict(seed=fixture['seed'],source=fixture['source_name'],block=fixture['block'],mode=mode,
                    raw_sha256=fixture['sha256'],predictions=a[:,4].astype(int).tolist(),
                    max_logit_absolute_error=float(np.max(abs(a[:,1:4]-np.asarray(fixture['expected_'+mode])))),matched=True));save()
        inspect('after')
        r.update(status='passed_independent_real_RF_ARM_full_frontend_CNN_matches_Python',test_frames_per_mode=54,
            independent_final_RX_idle=True,ARM_actual_execution=True,labels_used_by_inference=False,
            scratch_files_are_RAM_only=True,raw_evidence_not_modified=True)
    except Exception as e:r.update(status='failed_or_unconfirmed_ARM_verification',error=repr(e))
    finally:
        if board:
            if prompt_saved:
                try:board.command('stty echo');board.command('PS1=$p52_prompt')
                except Exception as e:r.update(status='failed_or_unconfirmed_ARM_verification',TTY_restore_error=repr(e))
            board.close()
        r['serial_closed']=True;save()
    print(out);print(r['status'])
    return 0 if r['status'].startswith('passed_') else 1
if __name__=='__main__':raise SystemExit(main())
