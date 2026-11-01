"""P201-specific uudecode restore, bounded and checked; no transmit operation."""
import argparse,base64,gzip,hashlib,io,json,re,tarfile,time
from datetime import datetime,timezone
from pathlib import Path
from p32_session import ROOT
from p46_console import Console as BoardConsole
from p35_once_merged_trial import AuditPort
from p46_known_source import source_bytes_valid,GUARD_SHA

def sha(b):return hashlib.sha256(b).hexdigest()

def validate_source_package(parent):
    p=json.loads(parent.read_text('utf-8'));payload=(parent.parent/'pkg.gz').read_bytes()
    allowed={'guard','source.c','sums','tone','bpsk','qpsk','qam16'}
    if (not p['guard_baseline_reproduced'] or p['source_peak_component_counts']!=256
        or set(p['files_sha256'])!=allowed or sha(payload)!=p['archive_sha256']
        or not 0<len(payload)<=4*1024*1024 or p['files_sha256']['guard']!=GUARD_SHA):
        raise ValueError('package provenance/size differs')
    files={name:(parent.parent/name).read_bytes() for name in allowed}
    if any(sha(raw)!=p['files_sha256'][name] for name,raw in files.items()):raise ValueError('host source changed')
    for name in ('tone','bpsk','qpsk','qam16'):source_bytes_valid(files[name])
    with gzip.GzipFile(fileobj=io.BytesIO(payload)) as stream:rawtar=stream.read(3*1024*1024+1)
    if len(rawtar)>3*1024*1024:raise ValueError('expanded archive too large')
    with tarfile.open(fileobj=io.BytesIO(rawtar)) as archive:
        members=archive.getmembers()
        if len(members)!=len(allowed) or {v.name for v in members}!=allowed or not all(v.isfile() for v in members):raise ValueError('archive member layout differs')
        for member in members:
            if archive.extractfile(member).read()!=files[member.name]:raise ValueError('archive and checked file differ')
    return p,payload,sha(rawtar)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-report',type=Path,required=True)
    parser.add_argument('--preflight',type=Path,required=True)
    args=parser.parse_args();parent=args.source_report.resolve();p,payload,tar_sha=validate_source_package(parent)
    fresh=json.loads(args.preflight.read_text('utf-8'))
    if fresh['status']!='read_only_both_boards_identified_DMA_idle' or not fresh['serial_closed']:raise ValueError('fresh dual-board idle preflight required')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=ROOT/'results'/('p46-restored-'+stamp);out.mkdir(exist_ok=False)
    d='/tmp/p35-p46u-'+stamp[9:15];r=dict(status='restoring',stages=[],remote_directory=d,
        expected_boot=fresh['boards']['COM9']['boot_id'],RX_expected_boot=fresh['boards']['COM8']['boot_id'],
        preflight=str(args.preflight.resolve()),preflight_sha256=sha(args.preflight.read_bytes()),
        source_report=str(parent),source_report_sha256=sha(parent.read_bytes()),files_sha256=p['files_sha256'],references=p['references'],
        RF_operations=False,RF_attribute_writes=False,PL_changes=False,source_peak_component_counts=256)
    (out/'executed.py').write_bytes(Path(__file__).read_bytes())
    def save():(out/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    board=None;decoder=False;echo_changed=False;save()
    try:
        board=BoardConsole('COM9',r,save);board.shell();board.port=AuditPort(board.port,out)
        if 'Linux pzp201' not in board.command('uname -a') or board.value('/proc/sys/kernel/random/boot_id')!=r['expected_boot'] or board.value('/proc/sys/kernel/tainted')!='0':raise ValueError('identity changed')
        if 'arm-tx-source' in board.command('ps'):raise ValueError('active TX')
        board.command('command -v uudecode');board.command('command -v gzip');board.command('command -v tar')
        board.command('mkdir '+d);board.command('d='+d);board.command('u=$d/pkg.gz')
        board.command('stty -echo');echo_changed=True
        board.port.write(b'echo __UU_READY__; uudecode -o $u; echo __UU_DONE__:$?\r');decoder=True
        banner=board.read(3,r'^__UU_READY__\r?$');r['decoder_banner']=banner;save()
        if '__UU_READY__' not in banner or '__UU_DONE__' in banner or 'not found' in banner:decoder=False;raise ValueError('decoder not waiting')
        board.port.write(b'begin-base64 600 pkg.gz\n');early=board.read(.4)
        if '__UU_DONE__' in early:decoder=False;raise ValueError('uudecode rejected base64 envelope')
        encoded=base64.b64encode(payload);lines=[encoded[i:i+76] for i in range(0,len(encoded),76)];sent=0;begin=time.monotonic();notice=begin
        for i in range(0,len(lines),16):
            pending=board.read(.01) if board.port.in_waiting else ''
            if '__UU_DONE__' in pending:decoder=False;raise ValueError('decoder exited during transfer')
            block=b'\n'.join(lines[i:i+16])+b'\n';board.port.write(block);sent+=len(block)
            delay=sent/9000-(time.monotonic()-begin)
            if delay>0:time.sleep(delay)
            if time.monotonic()-notice>30:print('P201 checked transfer '+str(round(100*sent/(len(encoded)+len(lines))))+'%',flush=True);notice=time.monotonic()
            if time.monotonic()-begin>300:raise ValueError('transfer time bound')
        board.port.write(b'====\n');tail=board.read(15,r'^__UU_DONE__:\d+\r?$');r['decoder_tail']=tail
        if not re.search(r'^__UU_DONE__:0\r?$',tail,re.M):raise ValueError('decode not completed')
        decoder=False;board.command('stty echo');echo_changed=False
        board.command('f='+d+'/pkg.gz');actual=board.command('sha256sum $f')
        if not re.search(r'^'+sha(payload)+r'\s',actual,re.M):raise ValueError('payload hash differs')
        board.command('gzip -dc $d/pkg.gz >$d/pkg.tar',timeout=20)
        r['uncompressed_archive_sha256']=tar_sha;board.command('v=$d/pkg.tar')
        if not re.search(r'^'+r['uncompressed_archive_sha256']+r'\s',board.command('sha256sum $v'),re.M):raise ValueError('uncompressed archive differs')
        board.command('tar -xf $d/pkg.tar -C $d');board.command('chmod 755 $d/guard');board.command('cd $d');board.command('sha256sum -c sums')
        for name,expected in p['files_sha256'].items():
            board.command('v='+d+'/'+name)
            if not re.search(r'^'+expected+r'\s',board.command('sha256sum $v'),re.M):raise ValueError('extracted member changed '+name)
        r['inspect']=board.command('./guard --inspect',timeout=15)
        for key,value in [('tx0_sampling_frequency','30720000'),('tx0_hardwaregain','-10.000000 dB'),('tx0_rf_bandwidth','18000000'),('tx0_rf_port_select','A'),('tx_lo','2450000000'),('TX_DMA_sampling_frequency','30720000')]:
            if key+'='+value not in r['inspect']:raise ValueError('guard config differs '+key)
        for i in range(8):
            if not re.search(r'^dds'+str(i)+r'_scale=0(?:\.0+)?\r?$',r['inspect'],re.M):raise ValueError('nonzero DDS scale')
        r['checks']={}
        for name in ('tone','bpsk','qpsk','qam16'):
            board.command('h='+r['files_sha256'][name]);value=board.command('./guard --check '+name+' 131072 $h')
            if 'INPUT_CHECK_PASS samples=131072' not in value:raise ValueError('file check rejected')
            r['checks'][name]=value;save()
        r['status']='guard_and_peak256_sources_restored_inspected_checked_no_TX'
    except Exception as e:r.update(status='failed_or_unconfirmed',error=repr(e))
    finally:
        if board:
            if decoder:board.port.write(b'\x03\r');board.read(.5)
            if echo_changed:
                try:board.command('stty echo')
                except Exception:pass
            board.close()
        r['serial_closed']=True;save();print(out);print(r['status'])
    return 0 if r['status'].startswith('guard_and_') else 1
if __name__=='__main__':raise SystemExit(main())
