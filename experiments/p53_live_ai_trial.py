"""Bounded three-class real RF + ARM CNN + LCD trial, no persistent deployment.

Peak256 / TX-10dB / RX0dB unchanged. One RX context per six-second case.
Each retained whole DMA block and framebuffer are archived before acceptance.
"""
import argparse,json,re,subprocess,sys,time
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
from PIL import Image
from p45_checkpoint import ROOT,read,write,sha,rel
from p46_console import Console
from p46_preflight import parse_names
from p46_known_source import GUARD_SHA
from p35_once_merged_trial import AuditPort
from p35_uart_files import upload
from p36_full_rx_run import RF_EXPECTED,CRITICAL_KERNEL
from p37_review_archives import archive_bytes,decode_rx12
from rfsig.rf_ai_calibration import adapt_calibrated
from rfsig.trainable_cnn import preprocess,patches,forward
from rfsig.cnn_quantization import quantized_forward
from p48_verify_units import glyph_mask
from p52_ram import board_ram_tmp


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',required=True,type=Path);args=p.parse_args()
    build=read(args.build)
    if build['status']!='passed_offline_live_AI_lifecycle_frontend_parity_ARM_build_not_deployed' or build['mock_cases']!=12:
        raise ValueError('complete offline live AI candidate required')
    for name,digest in build['inputs_sha256'].items():
        if sha(ROOT/name)!=digest:raise ValueError('candidate build input changed')
    binary=ROOT/build['binary']
    if sha(binary)!=build['binary_sha256']:raise ValueError('candidate binary changed')
    sources=read(ROOT/build['source_report'])
    if sha(ROOT/build['source_report'])!=build['source_sha256']:raise ValueError('restored TX source report changed')
    if sha(ROOT/build['ARM_review'])!=build['ARM_review_sha256']:raise ValueError('actual ARM acceptance changed')
    arm_review=read(ROOT/build['ARM_review']);frozen=read(ROOT/build['frozen'])
    if sha(ROOT/build['frozen'])!=build['frozen_sha256']:raise ValueError('model freeze changed')
    for v in frozen['frozen_inputs'].values():
        if sha(ROOT/v['path'])!=v['sha256']:raise ValueError('frozen inference input changed')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=ROOT/'results'/('p53-live-'+stamp);out.mkdir(exist_ok=False)
    r=dict(status='preflight',stages=[],cases=[],build=rel(args.build),build_sha256=sha(args.build),
        frozen=build['frozen'],frozen_sha256=build['frozen_sha256'],expected_boot=build.get('deployment_expected_boot',arm_review['expected_boot']),
        ARM_file_verification_boot=arm_review['expected_boot'],
        TX_expected_boot=sources['expected_boot'],serial_closed=False,persistent_deployment=False,
        RF_configuration_writes=False,PL_changes=False,TX_peak_component_counts=256,TX_hardwaregain_db=-10,
        TX_seconds_each=15,RX_duration_ms_each=6000,common_IF_hz=build['common_IF_hz'],selected_mode=build['selected_mode'],
        physical_LCD_confirmed=False,lossless_proven=False,confidence_calibrated=False,
        scope='three controlled known-source demonstrations; last full DMA independently checked; not arbitrary signals or continuous gap-free inference')
    def save():
        write(out/'report.json',r)
        s=read(ROOT/'TX-SOURCE-STATUS.json');s.update(status=r['status'],authoritative_current_field='p53_current')
        s['p53_current']=dict(report=rel(out/'report.json'),status=r['status'],serial_closed=r['serial_closed'],
            expected_boot=r['expected_boot'],startup_paused_for_archiving=True,AI_test_accepted=True,live_AI_finally_accepted=False)
        write(ROOT/'TX-SOURCE-STATUS.json',s);write(ROOT/'results/p53-active.json',s['p53_current'])
    rx=tx=None;rx_shell=tx_shell=False;active=None
    def digest(board,path):
        board.command('v='+path);found=re.findall(r'^([0-9a-f]{64})\s+\S+\r?$',board.command('sha256sum $v'),re.M)
        if len(found)!=1:raise ValueError('ambiguous remote SHA')
        return found[0]
    def names(board):
        board.command('ir=/sys/bus/iio/devices')
        return parse_names(board.command('for n in $ir/iio:device*;do echo __D__$n:$(cat $n/name)__E__;done'))
    def idle():
        if ('Zynq-Tronlong' not in rx.command('uname -a') or rx.value('/proc/sys/kernel/random/boot_id')!=r['expected_boot']
            or rx.value('/proc/sys/kernel/tainted')!='0'):raise ValueError('RX identity changed')
        if digest(rx,'/etc/rcS.d/S99board')!=sha(ROOT/'board/boot/S99board'):raise ValueError('paused startup guard changed')
        if re.search(r'/run/p42-\d+/monitor|iio_readdev|arm[-_]rx|arm-latest|p35-ai-\d+/a',rx.command('ps -ef')):raise ValueError('RX experiment active')
        n=names(rx);rx.command('cd '+n['ad9361-phy'])
        if {k:rx.value(k) for k in RF_EXPECTED}!=RF_EXPECTED:raise ValueError('RX settings changed')
        rx.command('cd '+n['cf-ad9361-lpc'])
        if rx.value('buffer/enable')!='0' or any(rx.value('scan_elements/in_voltage'+str(i)+'_en')!='0' for i in range(4)):raise ValueError('RX DMA not idle')
        if re.search(CRITICAL_KERNEL,rx.command('dmesg | tail -n 160')):raise ValueError('kernel error')
    def one_json(command):
        rows=[json.loads(line) for line in rx.command(command).splitlines() if line.startswith('{')]
        if len(rows)!=1:raise ValueError('ambiguous native JSON')
        return rows[0]
    save();(out/'executed.py').write_bytes(Path(__file__).read_bytes())
    try:
        for port in ('COM9','COM8'):
            board=Console(port,r,save)
            if port=='COM9':tx=board
            else:rx=board
            folder=out/port;folder.mkdir();board.port=AuditPort(board.port,folder);board.shell()
            if port=='COM9':tx_shell=True
            else:rx_shell=True
            board.command('p53_prompt=$PS1');board.command("PS1=''");board.command('stty -echo')
        idle()
        if ('Linux pzp201' not in tx.command('uname -a') or tx.value('/proc/sys/kernel/random/boot_id')!=r['TX_expected_boot']
            or tx.value('/proc/sys/kernel/tainted')!='0' or re.search('guard --run|arm-tx-source',tx.command('ps'))):raise ValueError('TX identity or active source differs')
        txnames=names(tx)
        for device in ('cf-ad9361-lpc','cf-ad9361-dds-core-lpc'):
            if tx.value(txnames[device]+'/buffer/enable')!='0':raise ValueError('TX-side DMA active')
        if digest(tx,sources['remote_directory']+'/guard')!=GUARD_SHA:raise ValueError('TX guard changed')
        r['resolved_RAM_tmp']=board_ram_tmp(rx);save()
        stage='/tmp/p35-ai-'+stamp[9:15];rx.command('mkdir '+stage)
        rx.command("PS1='# '");upload(rx,stage+'/a',binary.read_bytes())
        rx.command("PS1=''");rx.command('stty -echo');rx.command('chmod 755 '+stage+'/a')
        for name in ('bpsk','qpsk','qam16'):
            idle();case=dict(name=name,expected_class=('bpsk','qpsk','qam16').index(name),TX_started_maybe=False,TX_cleanup_verified=False)
            r['cases'].append(case);active=case;save();tx.command('cd '+sources['remote_directory'])
            if digest(tx,sources['remote_directory']+'/'+name)!=sources['files_sha256'][name]:raise ValueError('TX waveform changed')
            tx.command('p='+name);tx.command('h='+sources['files_sha256'][name]);tx.command('b=boot-session:'+r['TX_expected_boot'])
            tx.command('n=131072; f=30720000; l=2450000000; w=18000000')
            marker='__P53_TX_'+name+'__';case['marker']=marker;case['TX_started_maybe']=True;tx_shell=False;save()
            cmd='./guard --run $p $n $f $l $w -10 15 $b A $h RF_LINK_REVIEWED'
            tx.port.write((cmd+"\rprintf '\\n"+marker+":%s\\n' \"$?\"\r").encode('ascii'))
            case['TX_start']=tx.read(10,r'CYCLIC_PUSH_SUBMITTED samples=131072 deadline_seconds=15')
            if 'CYCLIC_PUSH_SUBMITTED samples=131072 deadline_seconds=15' not in case['TX_start']:raise ValueError('bounded TX submission unconfirmed')
            started=time.monotonic();print('Live RF AI/LCD '+name+' running',flush=True)
            directory='/tmp/p35-p53-'+stamp[9:15]+'-'+name
            rx.command('a='+stage+'/a');rx.command('o='+directory);rx.command('test ! -e $o')
            rx_shell=False
            try:case['native_stdout']=rx.command('timeout -k 2 12 $a $o 6000 500',timeout=16);rx_shell=True
            except Exception:
                if r['stages'] and isinstance(r['stages'][-1].get('exit_code'),int):rx_shell=True
                raise
            elapsed=time.monotonic()-started;case['RX_returned_seconds_after_TX_submission']=elapsed
            if elapsed>=14:raise ValueError('native RX not completed inside guarded source window')
            summary=one_json('cat $o/summary.json');ai=one_json('cat $o/ai.json');case.update(native_summary=summary,AI=ai,output_directory=directory)
            if (summary['status']!='pass' or summary['reason']!='duration_complete' or summary['display_revision']!='p53'
                or summary['display_updates']<5 or summary['retained_prefix_bytes']!=262144 or summary['prefix_frames']!=65536
                or not summary['worker_joined'] or not summary['buffer_released'] or not summary['context_released'] or summary['cleanup_unconfirmed']
                or not summary['RF_after_matches'] or summary['lossless_proven'] or summary['analyse_only']):raise ValueError('live native lifecycle gate failed')
            if (ai['predictions']!=[case['expected_class']]*3 or ai['source_block_sequence']!=summary['last_display_sequence']
                or ai['model_sha256']!=frozen['frozen_inputs']['model']['sha256'] or ai['common_IF_hz']!=build['common_IF_hz']
                or ai['mode']!=build['selected_mode'] or ai['confidence_calibrated']):raise ValueError('live AI final block gate failed')
            idle();save()
            for field,file,expected_bytes in (('IQ','last-display-packed.bin',262144),('FB','fb.raw',1536000)):
                raw=directory+'/'+file;digest_raw=digest(rx,raw)
                # Reuse only the reviewed retrieval path formats, in new folders.
                archive_dir='/tmp/p36-full-'+stamp[9:15]+'-'+name if field=='IQ' else '/tmp/p35-fb-'+stamp[9:15]+'-'+name
                rx.command('mkdir '+archive_dir);dest=archive_dir+('/iq-packed.bin.gz' if field=='IQ' else '/fb.raw.gz')
                rx.command('s='+raw);rx.command('z='+dest);rx.command('gzip -1 -c $s >$z',timeout=20);rx.command('gzip -t $z')
                count=re.findall(r'^__N__(\d+)__E__\r?$',rx.command('echo __N__$(wc -c <$s)__E__'),re.M)
                if count!=[str(expected_bytes)]:raise ValueError('native raw size differs')
                count=re.findall(r'^__N__(\d+)__E__\r?$',rx.command('echo __N__$(wc -c <$z)__E__'),re.M)
                if len(count)!=1:raise ValueError('gzip size ambiguous')
                case[field]=dict(remote=dest,expected_bytes=int(count[0]),expected_sha256=digest(rx,dest),raw_bytes=expected_bytes,raw_sha256=digest_raw);save()
            end=tx.read(20,r'^'+marker+r':\d+\r?$');case['TX_end']=end
            if (not re.search(r'^'+marker+r':0\r?$',end,re.M) or 'TX_CLEANUP buffer_released=true rf_settings_written=false status=0' not in end
                or 'DDS_ZERO_SOURCE_READBACK=PASS' not in end):raise ValueError('TX cleanup unconfirmed')
            tx_shell=True
            if tx.value(txnames['cf-ad9361-dds-core-lpc']+'/buffer/enable')!='0':raise ValueError('TX DMA remains active')
            tx.command('cd '+sources['remote_directory']);inspection=tx.command('./guard --inspect',timeout=15)
            case['TX_after']=inspection
            if any(not re.search(r'^dds'+str(i)+r'_raw=0(?:\.0+)?\r?$',inspection,re.M) for i in range(8)):raise ValueError('DDS zero source changed')
            case['TX_cleanup_verified']=True;active=None;save()
        idle();r.update(status='captured_live_AI_LCD_cases_pending_host_archive',independent_final_RX_idle=True)
    except Exception as e:
        r.update(status='failed_or_unconfirmed_live_AI',error=repr(e));save()
        if tx and active and active['TX_started_maybe'] and not tx_shell:
            try:
                tail=tx.read(20,r'^'+active['marker']+r':\d+\r?$');active['TX_error_tail']=tail
                tx_shell=bool(re.search(r'^'+active['marker']+r':\d+\r?$',tail,re.M))
            except Exception as e:r['TX_cleanup_error']=repr(e)
    finally:
        for board,confirmed in ((rx,rx_shell),(tx,tx_shell)):
            if board:
                if confirmed:
                    try:board.command('stty echo');board.command('PS1=$p53_prompt')
                    except Exception as e:r.update(status='failed_or_unconfirmed_live_AI',TTY_restore_error=repr(e))
                board.close()
        r.update(serial_closed=True,RX_shell_confirmed=rx_shell,TX_shell_confirmed=tx_shell);save()
    if r['status']=='captured_live_AI_LCD_cases_pending_host_archive':
        try:
            with np.load(ROOT/frozen['frozen_inputs']['model']['path'],allow_pickle=False) as z:model=dict(z)
            with np.load(ROOT/frozen['frozen_inputs']['quantized']['path'],allow_pickle=False) as z:q=dict(z)
            for case in r['cases']:
                for field in ('IQ','FB'):
                    entry=case[field];label=case['name']+'-'+field
                    cmd=[sys.executable,str(ROOT/'experiments/p36_retrieve_file.py'),'--expected-boot',r['expected_boot']]
                    for key in ('remote','expected_bytes','expected_sha256','raw_bytes','raw_sha256'):cmd.extend(['--'+key.replace('_','-'),str(entry[key])])
                    r.update(status='archiving_'+label,serial_closed=False);save();print('Archive '+label,flush=True)
                    child=subprocess.run(cmd,capture_output=True,timeout=400)
                    (out/(label+'.stdout')).write_bytes(child.stdout);(out/(label+'.stderr')).write_bytes(child.stderr);r['serial_closed']=True;save()
                    reports=[Path(s.strip())/'report.json' for s in child.stdout.decode().splitlines() if Path(s.strip()).is_absolute() and (Path(s.strip())/'report.json').is_file()]
                    if child.returncode or len(reports)!=1:raise ValueError('archive failed '+label)
                    entry.update(archive=rel(reports[0]),archive_sha256=sha(reports[0]))
                    meta,raw=archive_bytes(reports[0]);entry['host_verified']=True
                    if field=='IQ':
                        pairs=decode_rx12(raw);x=pairs[:,0].astype(float)+1j*pairs[:,1]
                        calibration=dict(status='known_tone_common_IF_calibrated',frequency_hz=build['common_IF_hz'],shared_across_modulation_classes=True,modulation_labels_used=False)
                        frames,_=adapt_calibrated(x,sample_rate_hz=30720000,calibration=calibration);tensor=patches(preprocess(np.asarray(frames,dtype=np.complex64)))
                        logits=forward(tensor,model) if build['selected_mode']=='fp32' else quantized_forward(tensor,q)
                        np.testing.assert_allclose(case['AI']['logits'],logits,rtol=1e-4,atol=5e-4)
                        if np.argmax(logits,1).tolist()!=case['AI']['predictions']:raise ValueError('live ARM/Python AI mismatch')
                        case['independent_AI_check']=True
                    else:
                        pixels=np.frombuffer(raw,dtype='<u4').reshape(480,800)
                        names=['BPSK','QPSK','16QAM'];a=case['AI'];text='AI: '+' / '.join(names[k] for k in a['predictions'])+' | '+format(a['full_frontend_CNN_ms'],'.1f')+' ms | controlled 3 classes'
                        mask=glyph_mask(text,ROOT/'embedded/arm_panel/font8x12.h');expected=np.where(mask,0xff96a5b6,0xff0c0e12).astype('<u4')
                        if not np.array_equal(pixels[456:468,16:16+mask.shape[1]],expected):raise ValueError('AI framebuffer glyphs differ')
                        image=out/(case['name']+'-screen.png');Image.frombytes('RGB',(800,480),raw,'raw','BGRX').save(image)
                        case.update(AI_framebuffer_pixels_exact=True,screen=rel(image))
                    save()
            r.update(status='passed_three_class_real_RF_live_ARM_AI_LCD_and_independent_archives',live_AI_on_LCD=True,
                last_AI_frames_verified=9,all_TX_cleanup_verified=True,independent_final_RX_idle=True,
                numeric_AI_check=True,framebuffer_AI_text_exact=True,serial_closed=True)
        except Exception as e:r.update(status='failed_or_unconfirmed_live_AI_archive_or_numeric_gate',error=repr(e))
        save()
    print(out);print(r['status']);return 0 if r['status'].startswith('passed_') else 1
if __name__=='__main__':raise SystemExit(main())
