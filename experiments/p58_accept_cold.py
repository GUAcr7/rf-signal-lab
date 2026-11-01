"""Read P57 after user-confirmed power cycling; no reboot or RX/PL launch."""
import argparse,re
from datetime import datetime,timezone
from pathlib import Path
from p45_checkpoint import ROOT,read,write,sha,rel
from p46_console import Console
from p35_once_merged_trial import AuditPort
from p46_preflight import parse_names
from p36_full_rx_run import RF_EXPECTED,CRITICAL_KERNEL

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--passive',required=True,type=Path);args=ap.parse_args();capture=read(args.passive)
    offpath=Path(capture['poweroff_report']);off=read(offpath);final=read(ROOT/off['final']);oldpath=ROOT/final['boot'];old=read(oldpath)
    if capture['status']!='passive_window_completed' or capture['UART_bytes_sent']!=0 or not capture['new_kernel_output_observed'] or not capture['startup_ready_observed'] or not capture['serial_closed']:raise ValueError('complete zero-byte passive startup proof required')
    if (args.passive.parent/'uart.tx.bin').read_bytes()!=b'' or sha(offpath)!=capture['poweroff_report_sha256'] or not off['halt_observed']:raise ValueError('passive/halt provenance differs')
    text=(args.passive.parent/'console.txt').read_text(encoding='utf-8');ids=re.findall(r'ORIGINAL_BACKUP_VERIFIED boot=([0-9a-f-]{36})',text)
    if len(ids)!=1 or ids[0]==off['expected_boot']:raise ValueError('new passive boot identity missing')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=ROOT/'results'/('p58-cold-'+stamp);out.mkdir();(out/'files').mkdir()
    human=out/'human-event.json';write(human,dict(source='direct user reply in current conversation',question='只断开新板电源约10秒后上电，原接线拨码和旧板不变',
        answer='新板已断电并重新上电',new_board_powercycled_by_user=True,host_reboot_substituted=False,old_boot=off['expected_boot']))
    for name,digest in old['installed_files_sha256'].items():
        p=oldpath.parent/'files'/name
        if sha(p)!=digest:raise ValueError('profile snapshot differs')
        (out/'files'/name).write_bytes(p.read_bytes())
    keys=('installed_directory','installed_files_sha256','previous_directory','previous_wrapper_sha256','armed_boot','TX_expected_boot',
        'bitstream_report','bitstream_report_sha256','overlay_report','overlay_report_sha256','work_directory','preparation','preparation_sha256')
    r={k:old[k] for k in keys};r.update(status='checking_cold_boot_read_only',stages=[],expected_boot=ids[0],host_launches_RX=False,
        reboots_issued=0,power_cycles_reported_by_user=1,true_power_cycle_verified=False,automatic_TX=False,serial_closed=False,
        human_event=rel(human),human_event_sha256=sha(human),passive=rel(args.passive),passive_sha256=sha(args.passive),
        console_sha256=sha(args.passive.parent/'console.txt'),poweroff=rel(offpath),poweroff_sha256=sha(offpath))
    b=None
    def save():
        write(out/'report.json',r);write(ROOT/'results/p58-active.json',dict(status=r['status'],report=rel(out/'report.json'),expected_boot=r['expected_boot'],serial_closed=r['serial_closed']))
    def digest(path):
        b.command('v='+path);q=re.findall(r'^([0-9a-f]{64})\s+\S+\r?$',b.command('sha256sum $v'),re.M)
        if len(q)!=1:raise ValueError('ambiguous SHA')
        return q[0]
    def one(command):
        import json
        rows=[json.loads(s) for s in b.command(command).splitlines() if s.startswith('{')]
        if len(rows)!=1:raise ValueError('one native JSON required')
        return rows[0]
    save()
    try:
        b=Console('COM8',r,save);b.port=AuditPort(b.port,out);b.shell();b.command('p58_prompt=$PS1');b.command("PS1=''");b.command('stty -echo')
        if b.value('/proc/sys/kernel/random/boot_id')!=ids[0] or b.value('/run/p43-init-boot')!=ids[0] or b.value('/proc/sys/kernel/tainted')!='0':raise ValueError('current boot/marker/taint differs')
        d=old['installed_directory'];b.command('d='+d);b.command('w='+old['work_directory'])
        for name,wanted in old['installed_files_sha256'].items():
            if digest(d+'/'+name)!=wanted:raise ValueError('installed profile changed')
        if digest('/etc/rcS.d/S99board')!=old['installed_files_sha256']['boot'] or digest(old['work_directory']+'/monitor')!=old['installed_files_sha256']['monitor']:raise ValueError('selected or RAM bytes differ')
        for p in ('$d/pending','$d/disabled','$w/exit','$w/control'):b.command('test ! -e '+p)
        log=b.command('cat /run/p43-boot.log');(out/'startup-log.txt').write_text(log,encoding='utf-8')
        for marker in ('ORIGINAL_BACKUP_VERIFIED','EMPTY_BINDINGS_VERIFIED','PL_ATTEMPT=1','OVERLAY_ATTEMPT=1','MONITOR_LAUNCH','PERSISTENT_MONITOR_READY'):
            if len(re.findall(r'^p43: '+re.escape(marker)+r'(?:\s|\r?$)',log,re.M))!=1 or len(re.findall(r'^p43: '+re.escape(marker)+r'(?:\s|\r?$)',text,re.M))!=1:raise ValueError('passive/live startup count differs')
        if 'FAILED:' in log:raise ValueError('startup failure')
        b.command('ir=/sys/bus/iio/devices');n=parse_names(b.command('for n in $ir/iio:device*;do echo __D__$n:$(cat $n/name)__E__;done'))
        b.command('cd '+n['ad9361-phy'])
        if {k:b.value(k) for k in RF_EXPECTED}!=RF_EXPECTED:raise ValueError('RX RF differs')
        if b.value(n['cf-ad9361-lpc']+'/buffer/enable')!='1' or re.search(CRITICAL_KERNEL,b.command('dmesg | tail -n 160')):raise ValueError('RX inactive or kernel fault')
        r['startup_AI']=one('cat $w/data/ai.json');r['startup_progress']=one('cat $w/data/progress.json');b.command('sleep 2');r['later_progress']=one('cat $w/data/progress.json')
        ai=r['startup_AI']
        if ai['boot_id']!=ids[0] or ai['state']!='CALIBRATION_REQUIRED' or ai['ready'] or ai['accepted_class']!=-1 or ai['calibration_token']!='':raise ValueError('old calibration reused')
        if r['later_progress']['display_updates']<=r['startup_progress']['display_updates'] or r['later_progress']['state']!='running':raise ValueError('autonomous progress absent')
        r.update(status='passed_P58_user_power_cycle_autonomous_RX_waits_for_fresh_calibration',monitor_started_by_board_init=True,RX_running=True,
            true_power_cycle_verified=True,fresh_empty_boot_verified=True,PL_programming_attempts=1,overlay_apply_attempts=1,persistent_AI_selected=True)
    except Exception as e:r.update(status='failed_or_unconfirmed_P58_cold_no_reboot_retry',error=repr(e))
    finally:
        if b:
            try:b.command('stty echo');b.command('PS1=$p58_prompt')
            except Exception as e:r['TTY_restore_error']=repr(e)
            b.close()
        r['serial_closed']=True;save();print(out);print(r['status'])
    return int(not r['status'].startswith('passed'))
if __name__=='__main__':raise SystemExit(main())
