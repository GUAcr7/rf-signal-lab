"""Prepare an exact guarded TX package on the PC only; never open a board port.

Upload is a separate P201-specific operation: p46_restore_tx.py requires both a
source report and a newly read preflight. The retired base64/tar-z route is gone.
"""
import argparse,gzip,hashlib,io,json,tarfile
from datetime import datetime,timezone
from pathlib import Path
from p32_session import ROOT
from rfsig.tx_waveforms import make_tx_waveform,pack_tx_iq_le16

def sha(b):return hashlib.sha256(b).hexdigest()
def read(p):return json.loads(p.read_text('utf-8'))
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--preflight',type=Path,required=True);args=p.parse_args()
    previous=read(args.preflight)
    if previous['status']!='read_only_both_boards_identified_DMA_idle' or not previous['serial_closed']:raise ValueError('preflight not accepted')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=ROOT/'results'/('p46-source-'+stamp);out.mkdir(exist_ok=False)
    r=dict(status='preparing_host_only',stages=[],board_operations=False,
        expected_boot=previous['boards']['COM9']['boot_id'],RX_expected_boot=previous['boards']['COM8']['boot_id'],
        preflight=str(args.preflight.resolve()),preflight_sha256=sha(args.preflight.read_bytes()),
        RF_operations=False,RF_attribute_writes=False,PL_changes=False,source_peak_component_counts=256)
    (out/'executed.py').write_bytes(Path(__file__).read_bytes())
    def save():(out/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    save()
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
        r['status']='host_peak256_source_package_prepared_not_uploaded'
    except Exception as e:r.update(status='failed_or_unconfirmed',error=repr(e))
    finally:
        r['serial_closed']=True;save();print(out);print(r['status'])
    return 0 if r['status']=='host_peak256_source_package_prepared_not_uploaded' else 1
if __name__=='__main__':raise SystemExit(main())
