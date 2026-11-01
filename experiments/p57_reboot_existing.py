"""One new controlled warm trial after archived prior data; no reinstall/hot retry."""
import argparse,re
from datetime import datetime,timezone
from pathlib import Path
from p45_checkpoint import ROOT,read,write,sha,rel
from p46_console import Console
from p35_once_merged_trial import AuditPort
from p46_preflight import parse_names
from p36_full_rx_run import RF_EXPECTED,CRITICAL_KERNEL

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--boot',required=True,type=Path);ap.add_argument('--archive',required=True,type=Path);args=ap.parse_args()
    old=read(args.boot);arc=read(args.archive);trial=read(ROOT/arc['trial'])
    if old['status']!='passed_P57_warm_boot_autonomous_RX_waits_for_fresh_calibration' or arc['status']!='passed_P56_full_history_and_IQ_pixels_byte_archived' or trial.get('boot_report_sha256')!=sha(args.boot):raise ValueError('archived preceding boot session required')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=ROOT/'results'/('p57-boot-'+stamp);out.mkdir();(out/'files').mkdir()
    for name,wanted in old['installed_files_sha256'].items():
        source=args.boot.parent/'files'/name
        if sha(source)!=wanted:raise ValueError('previous installed snapshot changed')
        (out/'files'/name).write_bytes(source.read_bytes())
    keys=('installed_directory','installed_files_sha256','previous_directory','previous_wrapper_sha256','armed_boot','TX_expected_boot',
        'bitstream_report','bitstream_report_sha256','overlay_report','overlay_report_sha256','work_directory','preparation','preparation_sha256')
    r={k:old[k] for k in keys};r.update(status='checking_archived_new_trial',stages=[],parent_boot=rel(args.boot),parent_boot_sha256=sha(args.boot),
        prior_archive=rel(args.archive),prior_archive_sha256=sha(args.archive),expected_boot=None,reboot_from_boot=old['expected_boot'],
        reboots_issued=0,host_launches_RX=False,true_power_cycle_verified=False,automatic_TX=False,serial_closed=False,profile_selected=False)
    def save():
        write(out/'report.json',r);write(ROOT/'results/p57-active.json',dict(status=r['status'],report=rel(out/'report.json'),expected_boot=r['expected_boot'],serial_closed=r['serial_closed']))
    b=None;save()
    def digest(path):
        b.command('v='+path);q=re.findall(r'^([0-9a-f]{64})\s+\S+\r?$',b.command('sha256sum $v'),re.M)
        if len(q)!=1:raise ValueError('ambiguous SHA')
        return q[0]
    def rf(idle):
        b.command('ir=/sys/bus/iio/devices');n=parse_names(b.command('for n in $ir/iio:device*;do echo __D__$n:$(cat $n/name)__E__;done'))
        b.command('cd '+n['ad9361-phy'])
        if {k:b.value(k) for k in RF_EXPECTED}!=RF_EXPECTED:raise ValueError('RX settings changed')
        b.command('cd '+n['cf-ad9361-lpc'])
        if b.value('buffer/enable')!=('0' if idle else '1') or b.value('/proc/sys/kernel/tainted')!='0':raise ValueError('DMA or taint differs')
        if idle and any(b.value('scan_elements/in_voltage'+str(i)+'_en')!='0' for i in range(4)):raise ValueError('scans active')
        if re.search(CRITICAL_KERNEL,b.command('dmesg | tail -n 160')):raise ValueError('kernel fault')
    def one(command):
        import json
        rows=[json.loads(s) for s in b.command(command).splitlines() if s.startswith('{')]
        if len(rows)!=1:raise ValueError('ambiguous native JSON')
        return rows[0]
    try:
        b=Console('COM8',r,save);b.port=AuditPort(b.port,out);b.shell();b.command('p57again_prompt=$PS1');b.command("PS1=''");b.command('stty -echo')
        if b.value('/proc/sys/kernel/random/boot_id')!=old['expected_boot']:raise ValueError('boot changed before trial')
        rf(True);d=old['installed_directory'];b.command('d='+d)
        for name,wanted in old['installed_files_sha256'].items():
            if digest(d+'/'+name)!=wanted:raise ValueError('installed bytes changed')
        b.command('test ! -e $d/pending');b.command('test ! -e $d/disabled')
        if digest('/etc/rcS.d/S99board')!=old['installed_files_sha256']['original']:raise ValueError('expected paused profile')
        b.command('z=/etc/rcS.d/.p57-switch');b.command('test ! -e $z');b.command('cp $d/boot $z');b.command('chmod 755 $z')
        if digest('/etc/rcS.d/.p57-switch')!=old['installed_files_sha256']['boot']:raise ValueError('switch differs')
        b.command('mv $z /etc/rcS.d/S99board');b.command('sync',timeout=20)
        r.update(status='new_controlled_trial_reboot_intent',profile_selected=True,reboots_issued=1);save();b.port.write(b'reboot\r')
        text=''
        for _ in range(2):
            text+=b.read(35,r'login:\s*$');(out/'boot-console.txt').write_text(text,encoding='utf-8')
            if re.search(r'login:\s*$',text):break
        if not re.search(r'U-Boot|Booting Linux|Linux version',text) or not re.search(r'login:\s*$',text):raise ValueError('new boot absent; no retry')
        b.shell();b.command('p57again_prompt=$PS1');b.command("PS1=''");b.command('stty -echo')
        boot=b.value('/proc/sys/kernel/random/boot_id');r['expected_boot']=boot;save()
        if boot in (old['expected_boot'],old['armed_boot']) or b.value('/run/p43-init-boot')!=boot:raise ValueError('new boot marker differs')
        b.command('d='+d);b.command('w='+old['work_directory']);b.command('test ! -e $d/pending');b.command('test ! -e $d/disabled')
        if digest('/etc/rcS.d/S99board')!=old['installed_files_sha256']['boot'] or digest(old['work_directory']+'/monitor')!=old['installed_files_sha256']['monitor']:raise ValueError('startup bytes differ')
        log=b.command('cat /run/p43-boot.log');(out/'startup-log.txt').write_text(log,encoding='utf-8')
        for marker in ('ORIGINAL_BACKUP_VERIFIED','EMPTY_BINDINGS_VERIFIED','PL_ATTEMPT=1','OVERLAY_ATTEMPT=1','MONITOR_LAUNCH','PERSISTENT_MONITOR_READY'):
            if len(re.findall(r'^p43: '+re.escape(marker)+r'(?:\s|\r?$)',log,re.M))!=1:raise ValueError('initialization count differs')
        if 'FAILED:' in log:raise ValueError('boot failed')
        r['startup_AI']=one('cat $w/data/ai.json');r['startup_progress']=one('cat $w/data/progress.json')
        if r['startup_AI']['state']!='CALIBRATION_REQUIRED' or r['startup_AI']['ready'] or r['startup_AI']['accepted_class']!=-1 or r['startup_AI']['boot_id']!=boot:raise ValueError('stale calibration at startup')
        rf(False);b.command('sleep 2');r['later_progress']=one('cat $w/data/progress.json')
        if r['later_progress']['display_updates']<=r['startup_progress']['display_updates']:raise ValueError('autonomous updates missing')
        r.update(status='passed_P57_warm_boot_autonomous_RX_waits_for_fresh_calibration',monitor_started_by_board_init=True,RX_running=True,
            fresh_empty_boot_verified=True,PL_programming_attempts=1,overlay_apply_attempts=1,persistent_AI_selected=True)
    except Exception as e:r.update(status='failed_or_unconfirmed_P57_boot_do_not_retry_hot',error=repr(e))
    finally:
        if b:
            try:b.command('stty echo');b.command('PS1=$p57again_prompt')
            except Exception as e:r['TTY_restore_error']=repr(e)
            b.close()
        r['serial_closed']=True;save();print(out);print(r['status'])
    return int(not r['status'].startswith('passed'))
if __name__=='__main__':raise SystemExit(main())
