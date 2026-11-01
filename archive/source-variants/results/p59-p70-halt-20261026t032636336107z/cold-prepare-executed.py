"""Save stopped P70 data, cleanly halt, or passively listen for user power-on."""
import argparse,re,time
from datetime import datetime,timezone
from pathlib import Path
from serial.tools import list_ports
from p45_checkpoint import ROOT,read,write,sha,rel
from p67_board_trial import control
from p46_console import Console
from p32_session import BoardConsole
from p35_once_merged_trial import AuditPort
from p68_evidence import archive
from rfsig.board_session import WORK,require_rx_control,require_tx_off

def archive_marker(text):
    payload=[s.strip() for s in text.splitlines() if s.strip() and not re.fullmatch(r'__P46_[0-9a-f]{8}__:\d+',s.strip())]
    if not payload:return None
    if len(payload)!=1:raise ValueError('ambiguous archive marker')
    match=re.fullmatch(r'([0-9a-f]{64})\s+'+re.escape(WORK+'/e.gz'),payload[0])
    if not match:raise ValueError('invalid archive marker')
    return match[1]

def halt(poweroff=True):
    with control.operation_lock():
        c=control.Controller('p70-halt');c.save();print(c.out,flush=True)
        (c.out/'cold-prepare-executed.py').write_bytes(Path(__file__).read_bytes())
        b=None;intent=False;save_tty=False
        c.record.update(status='P70_halt_preflight',halt_observed=False,poweroff_issued=False)
        try:
            c.status();rx=c.record['boards']['RX'];require_rx_control(rx,running=False);require_tx_off(c.record['boards']['TX'])
            if c.profile.get('schema')!='rfsig.receiver_profile.p70.v1':raise ValueError('selected P70 required')
            c.record.update(expected_boot=rx['boot_id'],selected_profile=c.record['provenance']['accepted_boot_report'],
                selected_profile_sha256=c.record['provenance']['accepted_boot_report_sha256'])
            b=Console(c.ports['RX'],c.record,c.save);folder=c.out/'halt-serial';folder.mkdir();b.port=AuditPort(b.port,folder);b.shell()
            identity=b.command('uname -a')
            if 'Zynq-Tronlong' not in identity or b.value('/proc/sys/kernel/random/boot_id')!=rx['boot_id']:raise ValueError('halt identity changed')
            b.command('p70h_prompt=$PS1');b.command('p70h_tty=$(stty -g)');save_tty=True;b.command("PS1=''");b.command('stty -echo')
            current=c.inspect('RX',b,identity);require_rx_control(current,running=False)
            c.record['stopped_RX']=current
            if 'p70' not in c.record['selected_profile']:raise ValueError('wrong profile provenance')
            b.command("grep -q ' /run tmpfs ' /proc/mounts")
            b.command('w='+WORK);c.record['chunks']=[]
            existing=archive_marker(c.optional(b,WORK+'/evidence-archive.sha'))
            if existing is None:
                b.command('test ! -e $w/e.tar')
                archive(c,b,WORK,('ai.json','ai-history.jsonl','metrics.json','metrics-history.jsonl','summary.json','progress.json','last-display-packed.bin','fb.raw'))
                b.command('v='+WORK+'/e.gz');b.command('sha256sum $v >$w/evidence-archive.sha')
            else:
                pointer=read(ROOT/'results/p70-stopped-archive-active.json');prior=ROOT/pointer['report'];saved=read(prior)
                if (sha(prior)!=pointer['report_sha256'] or saved['status']!='passed_P70_stopped_data_archived'
                    or saved.get('expected_boot')!=rx['boot_id'] or len(saved.get('files_sha256',{}))!=8
                    or saved.get('contract',{}).get('sha256')!=existing):raise ValueError('host archive proof missing/changed')
                for name,wanted in saved['files_sha256'].items():
                    if sha(prior.parent/'files'/name)!=wanted or c.digest(b,WORK+'/data/'+name)!=wanted:raise ValueError('stopped archive source/host changed')
                c.record.update(prior_archive=rel(prior),prior_archive_sha256=sha(prior),prior_archive_verified=True)
            for key,path in (('boot_log','/run/p43-boot.log'),('kernel_tail',None)):
                c.record[key]=b.command('dmesg | tail -n 160') if path is None else c.optional(b,path)
            if b.value('/proc/sys/kernel/random/boot_id')!=rx['boot_id']:raise ValueError('boot changed before halt')
            if not poweroff:
                c.record.update(status='passed_P70_stopped_data_archived',halt_observed=False)
            else:
                b.command('sync',timeout=20);c.record.update(status='P70_poweroff_intent',poweroff_issued=True);c.save();intent=True
                b.port.write(b'poweroff\r');text=b.read(20,r'System halted|Power down');c.record['poweroff_console']=text
                if not re.search(r'System halted|Power down',text):raise ValueError('halt not observed; no automatic retry')
                c.record.update(status='passed_P70_data_archived_System_halted',halt_observed=True)
        except Exception as e:c.record.update(status='failed_or_unconfirmed_P70_halt',error=repr(e))
        finally:
            if b:
                # After poweroff intent never send tty restoration bytes which
                # could later enter U-Boot. Passive listening is a separate task.
                if save_tty and not intent:
                    try:b.command('stty "$p70h_tty"');b.command('PS1=$p70h_prompt')
                    except Exception as e:c.record['TTY_restore_error']=repr(e)
                b.close()
            c.record['serial_closed']=True;c.save()
        write(ROOT/'results/p70-halt-active.json',dict(status=c.record['status'],report=rel(c.out/'report.json'),report_sha256=sha(c.out/'report.json')))
        if c.record['status']=='passed_P70_stopped_data_archived' and len(c.record.get('files_sha256',{}))==8:
            write(ROOT/'results/p70-stopped-archive-active.json',dict(report=rel(c.out/'report.json'),report_sha256=sha(c.out/'report.json')))
        print(c.record['status'],flush=True)
        return int(not c.record['status'].startswith('passed'))

def listen(halt_path):
    halted=read(halt_path)
    if halted['status']!='passed_P70_data_archived_System_halted' or not halted['serial_closed']:raise ValueError('saved halted new board required')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p70-passive-%Y%m%dT%H%M%SZ');out.mkdir()
    r=dict(status='opening_passive_listener',halt=rel(halt_path),halt_sha256=sha(halt_path),stages=[],
        UART_bytes_sent=0,serial_closed=False,old_boot=halted['expected_boot'],listening=False)
    def save():write(out/'report.json',r)
    b=None;text='';save();print(out,flush=True)
    try:
        ports=[p for p in list_ports.comports() if p.vid==0x1A86 and p.pid==0x7523]
        if len(ports)!=1:raise ValueError('unique RX CH340 missing')
        b=BoardConsole(ports[0].device,r,save);b.port=AuditPort(b.port,out)
        r.update(status='listening_no_UART_writes',listening=True,port=ports[0].device);save();print('P70_LISTENING_NO_WRITES',flush=True)
        end=time.monotonic()+1200
        while time.monotonic()<end:
            text+=b.read(1);(out/'console.txt').write_text(text,encoding='utf-8')
            if re.search(r'Linux version|Booting Linux',text) and 'PERSISTENT_MONITOR_READY' in text and re.search(r'login:\s*$',text):
                r.update(status='captured_P70_new_kernel_autonomous_ready_no_UART_writes',new_kernel_observed=True,startup_ready_observed=True);break
        else:raise TimeoutError('no fresh startup before passive deadline')
    except Exception as e:r.update(status='failed_or_unconfirmed_P70_passive',error=repr(e))
    finally:
        if b:b.close()
        r.update(serial_closed=True,listening=False);save();print(r['status'],flush=True)
    return int(not r['status'].startswith('captured'))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=('archive','halt','listen'));p.add_argument('--halt',type=Path);a=p.parse_args()
    raise SystemExit(listen(a.halt) if a.action=='listen' else halt(a.action=='halt'))
