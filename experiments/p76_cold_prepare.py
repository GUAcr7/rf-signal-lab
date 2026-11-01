"""Verify existing host archive, cleanly halt RX, or passively record power-on."""
import argparse,re,time
from datetime import datetime,timezone
from pathlib import Path
from serial.tools import list_ports
from p45_checkpoint import ROOT,read,write,sha,rel
from p67_board_trial import control
from p46_console import Console
from p32_session import BoardConsole
from p35_once_merged_trial import AuditPort
from p70_cold_prepare import passive_startup_ready
from rfsig.board_session import WORK,require_rx_control,require_tx_off


def halt(review_path):
    review=read(review_path);demo_path=ROOT/review['demo'];demo=read(demo_path)
    if (review['status']!='passed_P76_installed_10min_RF_history_FFT_pixels_cleanup'
        or sha(demo_path)!=review['demo_sha256'] or not all(g['passed'] for g in review['gates'])):
        raise ValueError('independently reviewed saved ten-minute session required')
    with control.operation_lock():
        c=control.Controller('p76-halt');r=c.record
        r.update(status='P76_halt_preflight',review=rel(review_path),review_sha256=sha(review_path),
                 demo=rel(demo_path),demo_sha256=sha(demo_path),halt_observed=False,poweroff_issued=False)
        (c.out/'executed-cold-prepare.py').write_bytes(Path(__file__).read_bytes());c.save();print(c.out,flush=True)
        b=None;intent=False;tty=False
        try:
            c.status();rx=r['boards']['RX'];require_rx_control(rx,running=False);require_tx_off(r['boards']['TX'])
            if c.profile['schema']!='rfsig.receiver_profile.p76.v1' or rx['boot_id']!=demo['expected_boot']:
                raise ValueError('installed session or boot changed')
            r['expected_boot']=rx['boot_id'];r['selected_boot']=c.record['provenance']['accepted_boot_report'];c.save()
            b=Console(c.ports['RX'],r,c.save);folder=c.out/'halt-serial';folder.mkdir();b.port=AuditPort(b.port,folder);b.shell()
            identity=b.command('uname -a')
            if 'Zynq-Tronlong' not in identity or b.value('/proc/sys/kernel/random/boot_id')!=rx['boot_id']:
                raise ValueError('halt console identity differs')
            b.command('p76_prompt=$PS1');b.command('p76_tty=$(stty -g)');tty=True
            b.command("PS1=''");b.command('stty -echo')
            current=c.inspect('RX',b,identity);require_rx_control(current,running=False)
            for name,digest in demo['files_sha256'].items():
                if sha(demo_path.parent/'files'/name)!=digest or c.digest(b,WORK+'/data/'+name)!=digest:
                    raise ValueError('saved source bytes differ '+name)
            r.update(prior_archive_verified=True,files_sha256=demo['files_sha256'],
                     boot_log=b.command('cat /run/p43-boot.log'),kernel_tail=b.command('dmesg | tail -n 160'))
            if b.value('/proc/sys/kernel/random/boot_id')!=rx['boot_id']:raise ValueError('boot changed before halt')
            b.command('sync',timeout=20);r.update(status='P76_poweroff_intent',poweroff_issued=True);c.save();intent=True
            b.port.write(b'poweroff\r');text=b.read(20,r'System halted|Power down');r['poweroff_console']=text
            if not re.search(r'System halted|Power down',text):raise ValueError('halt not observed; no automatic retry')
            r.update(status='passed_P76_saved_data_System_halted',halt_observed=True,RX_halted=True,
                     TX_stopped=True,RX_stopped=True,true_power_cycle_verified=False)
        except Exception as exc:r.update(status='failed_or_unconfirmed_P76_halt',error=repr(exc))
        finally:
            if b:
                if tty and not intent:
                    try:b.command('stty "$p76_tty"');b.command('PS1=$p76_prompt')
                    except Exception as exc:r['TTY_restore_error']=repr(exc)
                b.close()
            r['serial_closed']=True;c.save()
        write(ROOT/'results/p76-halt-active.json',dict(status=r['status'],report=rel(c.out/'report.json'),report_sha256=sha(c.out/'report.json')))
        print(r['status'],flush=True)


def listen(halt_path):
    prior=read(halt_path)
    if prior['status']!='passed_P76_saved_data_System_halted' or not prior['serial_closed']:
        raise ValueError('saved and halted P76 required')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p76-passive-%Y%m%dT%H%M%SZ');out.mkdir()
    r=dict(status='opening_P76_passive_listener',halt=rel(halt_path),halt_sha256=sha(halt_path),
           old_boot=prior['expected_boot'],UART_bytes_sent=0,serial_closed=False,listening=False,stages=[])
    def save():write(out/'report.json',r)
    (out/'executed-listener.py').write_bytes(Path(__file__).read_bytes());save();b=None;text='';print(out,flush=True)
    try:
        with control.operation_lock():
            ports=[p for p in list_ports.comports() if p.vid==0x1A86 and p.pid==0x7523]
            if len(ports)!=1:raise ValueError('unique RX CH340 absent')
            b=BoardConsole(ports[0].device,r,save);b.port=AuditPort(b.port,out)
            r.update(status='P76_listening_zero_UART_writes',port=ports[0].device,listening=True);save()
            print('P76_LISTENING_NO_WRITES',flush=True);end=time.monotonic()+1200
            while time.monotonic()<end:
                text+=b.read(1);(out/'console.txt').write_text(text,encoding='utf-8')
                if passive_startup_ready(text):
                    r.update(status='captured_P76_new_kernel_autonomous_ready_zero_writes',new_kernel_observed=True,startup_ready_observed=True);break
            else:raise TimeoutError('no startup before passive deadline')
    except Exception as exc:r.update(status='failed_or_unconfirmed_P76_passive',error=repr(exc))
    finally:
        if b:b.close()
        r.update(serial_closed=True,listening=False);save();print(r['status'],flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=('halt','listen'))
    ap.add_argument('--review',type=Path);ap.add_argument('--halt',type=Path);a=ap.parse_args()
    if a.action=='halt':halt(a.review)
    else:listen(a.halt)
