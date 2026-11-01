"""Run the proven finite sparse receiver with one non-resetting serial owner.

This reuses P27's binary/metadata contract for the snapshot panel. It does not
claim full IQ retention, continuity, RF signal identity, or physical visibility.
"""
import argparse
from datetime import datetime, timezone
import hashlib, json, re
from pathlib import Path
from p32_session import ROOT, BoardConsole
from p35_uart_files import upload
from p36_display_readback import AuditPort


def sha(data): return hashlib.sha256(data).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-boot',required=True)
    args=parser.parse_args()
    manifest_path=sorted(ROOT.glob('results/p27-native-build-*/report.json'))[-1]
    manifest=json.loads(manifest_path.read_text('utf-8'))
    binary=Path(manifest['binary']).read_bytes()
    if manifest['status']!='cross_compile_verified' or sha(binary)!=manifest['binary_sha256']:
        raise RuntimeError('native build changed')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out=ROOT/'results'/('p36-sparse-smoke-'+stamp);out.mkdir(exist_ok=False)
    directory='/tmp/p27-smoke-'+stamp[9:15]
    ram='/tmp/p35-smoke-'+stamp[9:15]
    report=dict(schema='rfsig.p36_sparse_smoke.v1',status='preflight',stages=[],
        expected_boot=args.expected_boot,build=str(manifest_path),output_directory=directory,
        RF_transmitted=False,RF_attribute_writes=False,PL_or_overlay_changes=False,
        complete_stream_saved=False,lossless_proven=False)
    (out/'executed.py').write_bytes(Path(__file__).read_bytes())
    (out/'build-report.json').write_bytes(manifest_path.read_bytes())
    def save(): (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    board=None
    def state():
        if board.value('/proc/sys/kernel/random/boot_id')!=args.expected_boot:
            raise RuntimeError('boot changed')
        if board.value('/proc/sys/kernel/tainted')!='0': raise RuntimeError('tainted kernel')
        board.command('cd '+adc)
        if board.value('buffer/enable')!='0' or any(board.value('scan_elements/in_voltage'+str(i)+'_en')!='0' for i in range(4)):
            raise RuntimeError('RX not independently idle')
    save()
    try:
        board=BoardConsole('COM8',report,save);board.port=AuditPort(board.port,out);board.shell()
        if 'Zynq-Tronlong' not in board.command('uname -a'):raise RuntimeError('wrong receiver')
        if re.search(r'arm-tx-source|p27-rx|arm-rx-capture|iio_readdev|p33-cancel|p36-full',board.command('ps -ef')):
            raise RuntimeError('active experiment')
        board.command('/etc/rcS.d/S99board --check-rf')
        board.command('p=/sys/bus/iio/devices')
        text=board.command('for d in $p/iio:device*; do echo $d; cat $d/name; done')
        names={n:p for p,n in re.findall(r'(/sys/bus/iio/devices/iio:device\d+)\r?\n([^\r\n]+)',text)}
        if not {'ad9361-phy','cf-ad9361-lpc','cf-ad9361-dds-core-lpc'}<=names.keys():raise RuntimeError('RF missing')
        adc=names['cf-ad9361-lpc'];state()
        board.command('mkdir '+ram);upload(board,ram+'/a',binary)
        board.command('p='+ram+'/a');board.command('chmod 755 $p')
        board.command('mkdir '+directory)
        report['status']='finite_capture';save()
        text=board.command('$p '+directory+' 16',timeout=20)
        if 'SPARSE_RX_PASS blocks=16' not in text or 'SPARSE_RX_RELEASED completed=16 status=0' not in text:
            raise RuntimeError('finite acceptance missing')
        board.command('cd '+directory)
        text=board.command('cat metadata.json')
        rows=[json.loads(line) for line in text.splitlines() if line.startswith('{')]
        if len(rows)!=1:raise RuntimeError('ambiguous native metadata')
        meta=rows[0];report['native_metadata']=meta
        if meta['blocks']!=16 or meta['channels']!=2 or not meta['buffer_released'] or meta['complete_stream_saved']:
            raise RuntimeError('sparse metadata mismatch')
        board.command('sha256sum prefixes.bin');board.command('cat before.txt after.txt')
        state();board.command('/etc/rcS.d/S99board --check-rf')
        log=board.command('dmesg | tail -n 100')
        if re.search(r'Internal error:|Kernel panic|Oops:|BUG:',log):raise RuntimeError('kernel error')
        report['status']='receiver_abi_layout_capture_and_release_verified'
    except Exception as exc:report.update(status='failed',error=repr(exc))
    finally:
        if board:board.close()
        report['serial_closed']=True;save();print(out);print(report['status'])
    return 0 if report['status']=='receiver_abi_layout_capture_and_release_verified' else 1

if __name__=='__main__':raise SystemExit(main())
