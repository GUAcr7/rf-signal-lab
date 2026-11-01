"""Read visible framebuffer bytes after a pinned snapshot draw; no display writes."""
import argparse
from datetime import datetime, timezone
import hashlib, json, re
from pathlib import Path
from p32_session import ROOT, BoardConsole
from p35_uart_files import upload
from p36_display_readback import AuditPort

def sha(data):return hashlib.sha256(data).hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-boot',required=True)
    parser.add_argument('--panel-report',type=Path,required=True)
    parser.add_argument('--build-report',type=Path,required=True)
    args=parser.parse_args()
    parent=json.loads(args.panel_report.read_text('utf-8'))
    build=json.loads(args.build_report.read_text('utf-8'))
    if parent['status']!='passed_frozen_sparse_analysis_and_framebuffer_draw_only' or parent['expected_boot']!=args.expected_boot:
        raise RuntimeError('accepted same-boot draw required')
    binary=Path(build['binary']).read_bytes()
    if build['status']!='passed_offline_geometry_and_ARM_cross_compile_not_board_test' or not all(c['passed'] for c in build['checks']) or sha(binary)!=build['binary_sha256'] or sha(Path(build['source']).read_bytes())!=build['source_sha256']:
        raise RuntimeError('dump build changed')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out=ROOT/'results'/('p36-fb-snapshot-'+stamp);out.mkdir(exist_ok=False)
    ram='/tmp/p35-fb-'+stamp[9:15]
    report=dict(schema='rfsig.p36_fb_snapshot_run.v1',status='preflight',stages=[],
        expected_boot=args.expected_boot,panel_report=str(args.panel_report.resolve()),
        build_report=str(args.build_report.resolve()),binary_sha256=sha(binary),
        framebuffer_writes=False,RF_operations=False,physical_panel_verified=False)
    (out/'executed.py').write_bytes(Path(__file__).read_bytes())
    def save():(out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    board=None
    def identity():
        if board.value('/proc/sys/kernel/random/boot_id')!=args.expected_boot or board.value('/proc/sys/kernel/tainted')!='0':raise RuntimeError('boot/taint changed')
    def digest(remote):
        board.command('p='+remote)
        text=board.command('sha256sum $p')
        found=re.findall(r'^([0-9a-f]{64})\s+\S+\r?$',text,re.M)
        if len(found)!=1:raise RuntimeError('ambiguous SHA')
        return found[0]
    save()
    try:
        board=BoardConsole('COM8',report,save);board.port=AuditPort(board.port,out);board.shell()
        if 'Zynq-Tronlong' not in board.command('uname -a'):raise RuntimeError('wrong board')
        identity();board.command('/etc/rcS.d/S99board --check-rf')
        if re.search(r'arm[-_]panel|arm[-_]rx|iio_readdev|p33-cancel|p36-full|p35-panel-[0-9TZ]+/a',board.command('ps -ef')):raise RuntimeError('active application')
        board.command('mkdir '+ram);upload(board,ram+'/a',binary)
        board.command('x='+ram);board.command('chmod 755 $x/a')
        text=board.command('$x/a $x/fb.raw',timeout=15)
        rows=[json.loads(line) for line in text.splitlines() if line.startswith('{')]
        if len(rows)!=1 or rows[0]['status']!='visible_bytes_saved' or rows[0]['bytes']!=1536000 or not rows[0]['geometry_unchanged']:
            raise RuntimeError('snapshot layout/bytes invalid')
        report['native_snapshot']=rows[0]
        raw=ram+'/fb.raw';report['raw_sha256']=digest(raw);report['raw_bytes']=1536000
        board.command('command -v gzip')
        board.command('test ! -e $x/fb.raw.gz')
        board.command('gzip -c $x/fb.raw > $x/fb.raw.gz',timeout=15)
        zipped=ram+'/fb.raw.gz';report['remote']=zipped;report['compressed_sha256']=digest(zipped)
        text=board.command('echo __BYTES__$(wc -c < $p)__END__')
        values=re.findall(r'^__BYTES__(\d+)__END__\r?$',text,re.M)
        if len(values)!=1:raise RuntimeError('ambiguous compressed bytes')
        report['compressed_bytes']=int(values[0]);identity()
        report['status']='visible_framebuffer_bytes_saved_and_gzip_verified_board_side'
    except Exception as exc:report.update(status='failed',error=repr(exc))
    finally:
        if board:board.close()
        report['serial_closed']=True;save();print(out);print(report['status'])
    return 0 if report['status'].startswith('visible_') else 1

if __name__=='__main__':raise SystemExit(main())
