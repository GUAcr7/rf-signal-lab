"""Restore exact guarded TX ELF and peak-256 references; inspect/check only, no TX."""
import argparse,gzip,hashlib,io,json,re,tarfile
from datetime import datetime,timezone
from pathlib import Path
from p32_session import ROOT,BoardConsole
from p35_once_merged_trial import AuditPort
from p35_uart_files import upload
from p46_preflight import parse_names
from rfsig.tx_waveforms import make_tx_waveform,pack_tx_iq_le16

def sha(b):return hashlib.sha256(b).hexdigest()
def read(p):return json.loads(p.read_text('utf-8'))
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--preflight',type=Path,required=True);args=p.parse_args()
    previous=read(args.preflight)
    if previous['status']!='read_only_both_boards_identified_DMA_idle' or not previous['serial_closed']:raise ValueError('preflight not accepted')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=ROOT/'results'/('p46-source-'+stamp);out.mkdir(exist_ok=False)
    remote='/tmp/p35-p46tx-'+stamp[9:15];r=dict(status='preparing',stages=[],remote_directory=remote,
        expected_boot=previous['boards']['COM9']['boot_id'],RX_expected_boot=previous['boards']['COM8']['boot_id'],
        preflight=str(args.preflight.resolve()),preflight_sha256=sha(args.preflight.read_bytes()),
        RF_operations=False,RF_attribute_writes=False,PL_changes=False,source_peak_component_counts=256)
    (out/'executed.py').write_bytes(Path(__file__).read_bytes())
    def save():(out/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    board=None;save()
    def digest(path):
        board.command('f='+path);v=re.findall(r'^([0-9a-f]{64})\s+\S+\r?$',board.command('sha256sum $f'),re.M)
        if len(v)!=1:raise ValueError('ambiguous SHA')
        return v[0]
    try:
        bundle=ROOT/'results/p13-upload-bundle-20261017T025802Z';meta=read(bundle/'report.json');data=(bundle/'board-session-bundle.tar').read_bytes()
        if sha(data)!='9af83ce980e9aa78214b6d50b170229564cf4e14940b1919d04a311c04afde9e':raise ValueError('archived guard package changed')
        with tarfile.open(fileobj=io.BytesIO(data)) as t:
            files={'guard':t.extractfile('stage/arm/arm-tx-source').read(),'source.c':t.extractfile('stage/arm/arm_tx_source.c').read()}
            original_tone=t.extractfile('stage/waveforms/tone-positive.iq16le').read()
        if sha(files['guard'])!=meta['arm_elf_sha256'] or sha(files['source.c'])!=meta['arm_source_sha256']:raise ValueError('guard provenance changed')
        options=dict(sample_rate_hz=30720000,samples_per_symbol=128,symbol_count=1024,seed=20261016,offset_hz=960000,rolloff=.35,span_symbols=10)
        if pack_tx_iq_le16(make_tx_waveform('tone',digital_peak_counts=512,**options).iq)!=original_tone:raise ValueError('tone generator baseline differs')
        moddir=ROOT/'results/p21-mod-waveforms-20261017T122536Z';modmeta=read(moddir/'report.json');references={}
        for name,mode in [('tone','tone'),('bpsk','BPSK'),('qpsk','QPSK'),('qam16','16QAM')]:
            wave=make_tx_waveform(mode,digital_peak_counts=256,**options);raw=pack_tx_iq_le16(wave.iq)
            if name!='tone':
                row=next(v for v in modmeta['waveforms'] if v['file']==name+'.iq16le')
                if raw!=(moddir/'bundle'/row['file']).read_bytes() or sha(raw)!=row['raw_sha256']:raise ValueError('modulation source differs '+name)
            files[name]=raw;references[name]=wave.reference
        files['sums']=''.join(sha(v)+'  '+n+'\n' for n,v in files.items()).encode('ascii')
        rawtar=io.BytesIO()
        with tarfile.open(fileobj=rawtar,mode='w') as t:
            for name,value in files.items():
                entry=tarfile.TarInfo(name);entry.size=len(value);entry.mode=0o755 if name=='guard' else 0o600;t.addfile(entry,io.BytesIO(value))
        payload=gzip.compress(rawtar.getvalue(),compresslevel=6,mtime=0)
        (out/'pkg.gz').write_bytes(payload)
        for name,value in files.items():(out/name).write_bytes(value)
        r.update(files_sha256={n:sha(v) for n,v in files.items()},references=references,archive_sha256=sha(payload),archive_bytes=len(payload),guard_baseline_reproduced=True);save()
        board=BoardConsole('COM9',r,save);board.port=AuditPort(board.port,out);board.shell()
        if 'Linux pzp201' not in board.command('uname -a') or board.value('/proc/sys/kernel/random/boot_id')!=r['expected_boot'] or board.value('/proc/sys/kernel/tainted')!='0':raise ValueError('TX identity changed')
        if re.search('arm-tx-source',board.command('ps')):raise ValueError('active TX')
        board.command('ir=/sys/bus/iio/devices');names=parse_names(board.command('for n in $ir/iio:device*;do echo __D__$n:$(cat $n/name)__E__;done'))
        for n in ('cf-ad9361-lpc','cf-ad9361-dds-core-lpc'):
            if board.value(names[n]+'/buffer/enable')!='0':raise ValueError('DMA active')
        board.command('mkdir '+remote);upload(board,remote+'/pkg.gz',payload);board.command('d='+remote)
        board.command('tar -xzf $d/pkg.gz -C $d');board.command('chmod 755 $d/guard');board.command('cd $d');board.command('sha256sum -c sums')
        for name,value in files.items():
            if digest(remote+'/'+name)!=sha(value):raise ValueError('board source changed '+name)
        r['inspect']=board.command('./guard --inspect',timeout=15)
        for key,value in [('tx0_sampling_frequency','30720000'),('tx0_hardwaregain','-10.000000 dB'),('tx0_rf_bandwidth','18000000'),('tx0_rf_port_select','A'),('tx_lo','2450000000'),('TX_DMA_sampling_frequency','30720000')]:
            if key+'='+value not in r['inspect']:raise ValueError('guard config differs '+key)
        for i in range(8):
            if not re.search(r'^dds'+str(i)+r'_scale=0(?:\.0+)?\r?$',r['inspect'],re.M):raise ValueError('DDS scale not zero')
        r['checks']={}
        for name in ('tone','bpsk','qpsk','qam16'):
            board.command('h='+r['files_sha256'][name]);v=board.command('./guard --check '+name+' 131072 $h')
            if 'INPUT_CHECK_PASS samples=131072' not in v:raise ValueError('native file check failed')
            r['checks'][name]=v;save()
        r['status']='guard_and_peak256_sources_restored_inspected_checked_no_TX'
    except Exception as e:r.update(status='failed_or_unconfirmed',error=repr(e))
    finally:
        if board:board.close()
        r['serial_closed']=True;save();print(out);print(r['status'])
    return 0 if r['status'].startswith('guard_and_') else 1
if __name__=='__main__':raise SystemExit(main())
