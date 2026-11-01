"""Execute the corrected ARM analysis on known fixtures, without framebuffer/RF."""
import argparse
from datetime import datetime,timezone
import hashlib,json,re
from pathlib import Path
from p32_session import ROOT,BoardConsole
from p35_uart_files import upload

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-boot',required=True)
    args=parser.parse_args()
    host=ROOT/'results/p35-arm-panel-check-20261020T161014Z'
    build=json.loads((host/'report.json').read_text('utf-8'))
    binary=Path(build['binary'])
    if build['status']!='passed_host_regressions_and_ARM_cross_compile_not_board_test' or sha(binary)!=build['binary_sha256'] or sha(Path(build['source']))!=build['source_sha256']:
        raise RuntimeError('final checked build changed')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out=ROOT/'results'/('p35-panel-board-'+stamp);out.mkdir(exist_ok=False)
    record=dict(status='preflight',stages=[],expected_boot=args.expected_boot,
        build_report=str(host/'report.json'),source_sha256=build['source_sha256'],
        binary_sha256=build['binary_sha256'],RF_operations=False,
        framebuffer_operations=False,live_capture=False,known_fixture_only=True,checks=[])
    def save():(out/'report.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    def check(name,condition):
        record['checks'].append(dict(name=name,passed=bool(condition)));save()
        if not condition:raise RuntimeError(name)
    board=None
    try:
        board=BoardConsole('COM8',record,save);board.shell()
        check('receiver identity','Zynq-Tronlong' in board.command('uname -a'))
        check('expected boot',board.value('/proc/sys/kernel/random/boot_id')==args.expected_boot)
        check('untainted before',board.value('/proc/sys/kernel/tainted')=='0')
        processes=board.command('ps -ef')
        check('no capture/application active',not re.search(r'p27-rx|p33-cancel|arm-rx-capture|iio_readdev|arm-tx-source',processes))
        directory='/tmp/p35-panel-'+stamp[9:15]
        board.command('mkdir '+directory)
        files={'a':binary,'p':host/'positive.iq','n':host/'negative.iq','z':host/'zero.iq'}
        record['uploaded']={}
        for remote_name,local in files.items():
            data=local.read_bytes();(out/remote_name).write_bytes(data)
            record['uploaded'][remote_name]=dict(source=str(local),bytes=len(data),sha256=upload(board,directory+'/'+remote_name,data))
            save()
        board.command('d='+directory)
        board.command('chmod 755 $d/a')
        metrics=[]
        for file,channels,frames,expected_bin in [('p',2,1,73),('p',2,8,73),('n',4,8,-137),('z',2,8,None)]:
            output=board.command(f'$d/a --analyse-only $d/{file} {channels} {frames} 1',timeout=12)
            rows=[json.loads(s) for s in output.splitlines() if s.startswith('{')]
            check('one metrics row '+file+str(frames),len(rows)==1)
            row=rows[0];metrics.append(row)
            check('metrics schema '+file+str(frames),row['schema']=='rfsig.arm_panel_metrics.v2')
            check('bin '+file+str(frames),row['peak_offset_bins']==expected_bin)
            check('peak validity '+file+str(frames),row['peak_valid']==(expected_bin is not None))
            check('no draw/refresh claim '+file+str(frames),row['analyse_only'] and row['draw_ms']==0 and not row['display_refresh_measured'] and not row['capture_throughput_measured'])
            if expected_bin is not None:
                check('power normalized '+file+str(frames),abs(row['peak_db']-58.2394)<.002)
                check('component RMS '+file+str(frames),abs(row['rms_per_component_counts']-707.13)<.1)
        check('1 and 8 frames no level drift',abs(metrics[0]['peak_db']-metrics[1]['peak_db'])<.001)
        record['metrics']=metrics
        check('same boot after',board.value('/proc/sys/kernel/random/boot_id')==args.expected_boot)
        check('untainted after',board.value('/proc/sys/kernel/tainted')=='0')
        board.command('/etc/rcS.d/S99board --check-rf')
        record['status']='passed_corrected_ARM_analysis_known_fixtures_no_framebuffer_test'
    except Exception as exc:record.update(status='failed',error=repr(exc))
    finally:
        if board:board.close()
        record['serial_closed']=True;save();print(out);print(record['status'])
    return 0 if record['status'].startswith('passed_') else 1

if __name__=='__main__':raise SystemExit(main())
