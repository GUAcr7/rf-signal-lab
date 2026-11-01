"""Read ended P42 runtime footprint and final progress, without board file writes."""
import argparse
from datetime import datetime,timezone
import hashlib,json,re
from pathlib import Path
from p32_session import ROOT,BoardConsole
from p35_once_merged_trial import AuditPort
from p36_fb_snapshot_run import accepted_panel_parent

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--trial',required=True,type=Path);args=p.parse_args()
    trial=json.loads(args.trial.read_text('utf-8'));boot=trial['expected_boot'];ram=trial['RAM_directory']
    if trial.get('schema')!='rfsig.p42_board.v1' or not accepted_panel_parent(trial,boot) or not re.fullmatch(r'/run/p42-\d{6}',ram):raise ValueError('accepted completed P42 RAM parent required')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p42-runtime-readback-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    r=dict(status='preflight',stages=[],expected_boot=boot,trial=str(args.trial.resolve()),
        trial_sha256=hashlib.sha256(args.trial.read_bytes()).hexdigest(),board_file_writes=False,RF_operations=False)
    (out/'executed.py').write_bytes(Path(__file__).read_bytes())
    def save():(out/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    board=None;save()
    try:
        board=BoardConsole('COM8',r,save);board.port=AuditPort(board.port,out);board.shell()
        def identity():
            if board.value('/proc/sys/kernel/random/boot_id')!=boot or board.value('/proc/sys/kernel/tainted')!='0':raise RuntimeError('boot/taint changed')
        identity()
        if 'Zynq-Tronlong' not in board.command('uname -a'):raise RuntimeError('wrong board')
        if not re.search(r'^\S+ /run tmpfs \S+',board.command('cat /proc/mounts'),re.M):raise RuntimeError('/run is not tmpfs')
        if re.search(r'/run/p42-\d+/monitor|arm-latest|iio_readdev',board.command('ps -ef')):raise RuntimeError('monitor still active')
        board.command('x='+ram)
        text=board.command('find $x -type f');files=re.findall(r'^'+re.escape(ram)+r'/([^\r\n]+)\r?$',text,re.M)
        expected=['monitor','run','pid','exit','log','data/progress.json','data/summary.json',
            'data/last-display-packed.bin','data/last-display-packed.bin.gz']
        if sorted(files)!=sorted(expected):raise RuntimeError('runtime files differ; no unbounded history allowed')
        r['files']=files
        sizes={}
        for path in files:
            board.command('f='+ram+'/'+path)
            values=re.findall(r'^__N__(\d+)__E__\r?$',board.command('echo __N__$(wc -c <$f)__E__'),re.M)
            if len(values)!=1:raise RuntimeError('ambiguous file size')
            sizes[path]=int(values[0])
        if sizes['log']!=trial['native_log_bytes'] or sizes['log']>4096 or sizes['data/progress.json']>4096 or sizes['data/last-display-packed.bin']!=32768:raise RuntimeError('size bound differs')
        values=re.findall(r'^(\d+)\s+'+re.escape(ram)+r'\r?$',board.command('du -sk $x'),re.M)
        if len(values)!=1 or int(values[0])>256:raise RuntimeError('runtime footprint exceeded 256 KiB')
        board.command('g=$x/data/progress.json')
        rows=[json.loads(line) for line in board.command('cat $g').splitlines() if line.startswith('{')]
        if rows!=[trial['progress_samples'][-1]]:raise RuntimeError('final atomic progress changed')
        identity()
        r.update(status='passed_ended_P42_RAM_file_layout_and_bounded_footprint_readback',
            sizes=sizes,allocated_KiB=int(values[0]),runtime_footprint_bound_KiB=256,
            progress_unchanged=True,no_history_files=True,ADC_gaps='unknown',lossless_proven=False)
    except Exception as exc:r.update(status='failed',error=repr(exc))
    finally:
        if board:board.close()
        r['serial_closed']=True;save();print(out);print(r['status'])
    return 0 if r['status'].startswith('passed_') else 1

if __name__=='__main__':raise SystemExit(main())
