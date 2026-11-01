"""Install P69 as a separate P70 startup profile; one ordinary reboot only."""
import json,re,subprocess,time,xml.etree.ElementTree as ET
from datetime import datetime,timezone
from pathlib import Path
from p45_checkpoint import ROOT,read,write,sha,rel
from p67_board_trial import control
from p35_uart_files import upload
from p52_ram import board_ram_tmp
from p57_boot_templates import render
from p36_build_rx_full import posix
from rfsig.board_session import WORK,require_rx_control,require_tx_off,one_json

def main():
    review_path=ROOT/'results/p69-board-review-20261026T030150Z/report.json';review=read(review_path)
    build_path=ROOT/review['build'];build=read(build_path)
    if review['status']!='passed_P69_native_ROI_RF_AI_pixels_and_invalidation' or sha(build_path)!=review['build_sha256']:raise ValueError('actual P69 review required')
    if sha(ROOT/build['binary'])!=review['binary_sha256']:raise ValueError('reviewed binary changed')
    for p,h in build['inputs_sha256'].items():
        if sha(ROOT/p)!=h:raise ValueError('candidate build input changed '+p)
    for name,count in (('p70-controller-tests-20261026.xml',66),('p70-startup-tests-20261026.xml',15)):
        cases=list(ET.parse(ROOT/'results'/name).getroot().iter('testcase'))
        if len(cases)!=count or any(list(c.iter(k)) for c in cases for k in ('error','failure','skipped')):raise ValueError('offline acceptance '+name)
    config=ROOT/'configs/receiver-profile.json'
    if config.exists():raise ValueError('receiver already selected; no reinstall/reboot retry')
    with control.operation_lock():
        c=control.Controller('p70-install');old_out=c.out
        stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=ROOT/'results'/('p70-boot-'+stamp);out.mkdir();c.out=out
        original_save=c.save
        def save():
            original_save()
            write(ROOT/'results/p70-active.json',dict(status=c.record['status'],report=rel(out/'report.json'),
                report_sha256=sha(out/'report.json'),profile_selected=c.record.get('profile_selected',False),
                RX_running=c.record.get('RX_running'),true_power_cycle_verified=False))
        c.save=save
        c.record.update(schema='rfsig.receiver_profile.p70.v1',status='P70_preflight',controller_initial_record=rel(old_out/'report.json'),
            accepted_review=rel(review_path),accepted_review_sha256=sha(review_path),build=rel(build_path),build_sha256=sha(build_path),
            binary_sha256=review['binary_sha256'],reboots_issued=0,true_power_cycle_verified=False,
            monitor_started_by_board_init=False,profile_selected=False,serial_closed=False)
        (out/'executed.py').write_bytes(Path(__file__).read_bytes());c.save();print(out,flush=True)
        try:
            c.status();old=c.profile.copy();provenance=c.record['provenance']
            tx=c.record['boards']['TX'];rx=c.record['boards']['RX'];require_tx_off(tx);require_rx_control(rx,running=False)
            c.record.update(previous_profile_report=provenance['accepted_boot_report'],
                previous_profile_report_sha256=provenance['accepted_boot_report_sha256'],previous_directory=old['installed_directory'],
                previous_wrapper_sha256=old['installed_files_sha256']['boot'],armed_boot=rx['boot_id'],TX_expected_boot=tx['boot_id'])
            previous=Path(provenance['accepted_boot_report']).parent/'files'
            lines=(previous/'bringup').read_text(encoding='ascii').splitlines()
            hardware=dict(line.split('=',1) for line in lines if re.match(r'^(BIT|BIT_SHA|DTBO|DTBO_SHA)=',line))
            directory='/etc/p43-'+stamp
            files=render(directory,rx['boot_id'],review['binary_sha256'],hardware['BIT'],hardware['BIT_SHA'],hardware['DTBO'],hardware['DTBO_SHA'])
            files['monitor']=(ROOT/build['binary']).read_bytes();files['previous-boot']=(previous/'boot').read_bytes()
            for name in ('original','control','run'):
                if files[name]!=(previous/name).read_bytes():raise ValueError('unexpected launcher/control change '+name)
            normalized=files['bringup'].decode('ascii').replace(directory,old['installed_directory'])
            normalized=normalized.replace(review['binary_sha256'],old['installed_files_sha256']['monitor'])
            normalized=normalized.replace(rx['boot_id'],old['armed_boot'])
            if normalized!=(previous/'bringup').read_text(encoding='ascii'):raise ValueError('hardware startup changed beyond app/profile identities')
            normalized=files['boot'].decode('ascii').replace(directory,old['installed_directory'])
            import hashlib
            normalized=normalized.replace(hashlib.sha256(files['bringup']).hexdigest(),old['installed_files_sha256']['bringup'])
            normalized=normalized.replace(rx['boot_id'],old['armed_boot'])
            if normalized!=(previous/'boot').read_text(encoding='ascii'):raise ValueError('boot guard changed beyond profile identities')
            (out/'files').mkdir()
            for name,data in files.items():(out/'files'/name).write_bytes(data)
            c.record.update(installed_directory=directory,installed_files_sha256={name:sha(out/'files'/name) for name in files},
                expected_native_duration_ms=900000,work_directory=WORK,hardware=hardware)
            for name in ('boot','bringup','control','run'):
                q=subprocess.run(['wsl.exe','--exec','sh','-n',posix(out/'files'/name)],capture_output=True,timeout=15)
                (out/(name+'-syntax.stderr')).write_bytes(q.stderr)
                if q.returncode:raise ValueError('shell syntax '+name)
            c.save()
            with c.board('RX') as (b,identity):
                fresh=c.inspect('RX',b,identity);require_rx_control(fresh,running=False)
                if fresh['boot_id']!=rx['boot_id']:raise ValueError('preinstall boot changed')
                for path,wanted in ((hardware['BIT'],hardware['BIT_SHA']),(hardware['DTBO'],hardware['DTBO_SHA'])):
                    if c.digest(b,path)!=wanted:raise ValueError('cached hardware changed')
                c.record['RAM_tmp']=board_ram_tmp(b);stage='/tmp/p35-p70-'+stamp[9:15]
                b.command('s='+stage);b.command('test ! -e $s');b.command('mkdir $s')
                for name,data in files.items():
                    b.command("PS1='# '");upload(b,stage+'/'+name,data);b.command("PS1=''");b.command('stty -echo')
                b.command('d='+directory);b.command('test ! -e $d');b.command('mkdir $d')
                for name in files:
                    b.command('cp $s/'+name+' $d/'+name);b.command('chmod 755 $d/'+name)
                    if c.digest(b,directory+'/'+name)!=c.record['installed_files_sha256'][name]:raise ValueError('installed hash '+name)
                for name in ('boot','bringup','control','run'):b.command('sh -n $d/'+name)
                if c.digest(b,'/etc/rcS.d/S99board')!=c.record['previous_wrapper_sha256']:raise ValueError('old selection changed')
                if c.digest(b,directory+'/previous-boot')!=c.record['previous_wrapper_sha256']:raise ValueError('fallback snapshot changed')
                if b.value('/proc/sys/kernel/random/boot_id')!=rx['boot_id']:raise ValueError('boot changed before commit')
                b.command('sync',timeout=20);b.command('z=/etc/rcS.d/.p70-switch');b.command('test ! -e $z')
                b.command('cp $d/boot $z');b.command('chmod 755 $z')
                if c.digest(b,'/etc/rcS.d/.p70-switch')!=c.record['installed_files_sha256']['boot']:raise ValueError('selection staging changed')
                c.record.update(status='P70_committing_selection');c.save()
                b.command('mv $z /etc/rcS.d/S99board');b.command('sync',timeout=20)
                if c.digest(b,'/etc/rcS.d/S99board')!=c.record['installed_files_sha256']['boot']:raise ValueError('selection commit changed')
                c.record.update(profile_selected=True,status='P70_ordinary_reboot_intent',reboots_issued=1);c.save()
                b.port.write(b'reboot\r');text=''
                for _ in range(2):
                    text+=b.read(35,r'login:\s*$');(out/'boot-console.txt').write_text(text,encoding='utf-8')
                    if re.search(r'login:\s*$',text):break
                if not re.search(r'U-Boot|Booting Linux|Linux version',text) or not re.search(r'login:\s*$',text):raise ValueError('fresh kernel/login missing; no retry')
                b.shell();b.command('p59_prompt=$PS1');b.command('p59_tty=$(stty -g)');b.command("PS1=''");b.command('stty -echo')
                boot=b.value('/proc/sys/kernel/random/boot_id');c.record['expected_boot']=boot;c.save()
                if boot==rx['boot_id'] or b.value('/run/p43-init-boot')!=boot:raise ValueError('new boot/init proof missing')
                b.command('d='+directory);b.command('test ! -e $d/pending');b.command('test ! -e $d/disabled')
                log=b.command('cat /run/p43-boot.log');(out/'startup-log.txt').write_text(log,encoding='utf-8')
                for marker in ('ORIGINAL_BACKUP_VERIFIED','EMPTY_BINDINGS_VERIFIED','PL_ATTEMPT=1','OVERLAY_ATTEMPT=1','MONITOR_LAUNCH','PERSISTENT_MONITOR_READY'):
                    if len(re.findall(r'^p43: '+re.escape(marker)+r'(?:\s|\r?$)',log,re.M))!=1:raise ValueError('startup marker '+marker)
                if 'FAILED:' in log:raise ValueError('startup failure')
                if c.digest(b,WORK+'/monitor')!=review['binary_sha256']:raise ValueError('wrong running app')
                c.profile=dict(installed_directory=directory,installed_files_sha256=c.record['installed_files_sha256'])
                first=c.inspect('RX',b,identity);require_rx_control(first,running=True)
                metric=one_json(c.optional(b,WORK+'/data/metrics.json'))
                if first['AI']['state']!='CALIBRATION_REQUIRED' or first['AI']['ready'] or metric['valid'] or metric['measurement_status']!='CALIBRATION_REQUIRED':raise ValueError('unsafe startup measurement/calibration')
                time.sleep(5);later=c.inspect('RX',b,identity);require_rx_control(later,running=True)
                if later['progress']['display_updates']<=first['progress']['display_updates']:raise ValueError('no autonomous UI updates')
                c.record.update(status='passed_P70_warm_boot_autonomous_ROI_display',startup_RX=first,later_RX=later,
                    startup_metrics=metric,monitor_started_by_board_init=True,automatic_TX=False,
                    physical_LCD_confirmed=False,RX_running=True,TX_stopped=True)
            c.record['serial_closed']=True;c.save()
            write(config,dict(schema='rfsig.selected_receiver_profile.v1',report=rel(out/'report.json'),report_sha256=sha(out/'report.json')))
            # Validate the exact persisted selection before returning control.
            from rfsig.receiver_profile import selected_profile
            selected_profile(ROOT,old,provenance)
        except Exception as e:
            c.record.update(status='failed_or_unconfirmed_P70_install_no_hot_retry',error=repr(e),serial_closed=True);c.save()
        write(ROOT/'results/p70-active.json',dict(status=c.record['status'],report=rel(out/'report.json'),report_sha256=sha(out/'report.json'),
            profile_selected=c.record['profile_selected'],RX_running=c.record.get('RX_running'),true_power_cycle_verified=False))
        print(c.record['status'],flush=True);return int(not c.record['status'].startswith('passed'))
if __name__=='__main__':raise SystemExit(main())
