"""Install independent AI startup profile and try one ordinary reboot, never hot PL."""
import argparse,re,time
from datetime import datetime,timezone
from pathlib import Path
from p45_checkpoint import ROOT,read,write,sha,rel
from p46_console import Console
from p46_preflight import parse_names
from p35_once_merged_trial import AuditPort,validate_inputs
from p35_uart_files import upload
from p36_full_rx_run import RF_EXPECTED,CRITICAL_KERNEL
from p57_boot_templates import render,WORK
from p52_ram import board_ram_tmp

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--preparation',required=True,type=Path);ap.add_argument('--preflight',required=True,type=Path);args=ap.parse_args()
    p=read(args.preparation);fresh=read(args.preflight);oldpath=ROOT/'results/p43-enabled-20261024T091617Z/report.json';old=read(oldpath)
    if p['status']!='passed_P57_startup_control_15_offline_cases_not_boot_test' or p['test_count']!=15:raise ValueError('offline startup gates required')
    for name,digest in p['inputs_sha256'].items():
        if sha(ROOT/name)!=digest:raise ValueError('tested source changed')
    if fresh['status']!='read_only_both_boards_identified_DMA_idle' or fresh['boards']['COM8']['boot_id']!=old['expected_boot']:raise ValueError('fresh idle accepted P48 profile required')
    prior=read(ROOT/'results/p35-once-merged-20261022T022336Z/report.json')
    bitpath=Path(prior['bitstream_report']);overlaypath=Path(prior['overlay_report']);bit,overlay,binbytes,dtbobytes=validate_inputs(bitpath,overlaypath)
    # Use the exact cached pair already present in the accepted P48 profile.
    lines=(ROOT/'results/p55-recovery-cycle-20261024T075939Z/files/bringup').read_text().splitlines()
    fields=dict(line.split('=',1) for line in lines if re.match(r'^(BIT|BIT_SHA|DTBO|DTBO_SHA)=',line))
    import hashlib
    if hashlib.sha256(binbytes).hexdigest()!=fields['BIT_SHA'] or hashlib.sha256(dtbobytes).hexdigest()!=fields['DTBO_SHA']:raise ValueError('cached pair differs from accepted safe artifacts')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');directory='/etc/p43-'+stamp
    files=render(directory,old['expected_boot'],p['binary_sha256'],fields['BIT'],fields['BIT_SHA'],fields['DTBO'],fields['DTBO_SHA'])
    files['monitor']=(ROOT/p['binary']).read_bytes()
    if hashlib.sha256(files['monitor']).hexdigest()!=p['binary_sha256']:raise ValueError('native binary differs')
    out=ROOT/'results'/('p57-boot-'+stamp);out.mkdir();(out/'files').mkdir()
    for name,data in files.items():(out/'files'/name).write_bytes(data)
    r=dict(status='checking',stages=[],preparation=rel(args.preparation),preparation_sha256=sha(args.preparation),preflight=rel(args.preflight),preflight_sha256=sha(args.preflight),
        previous_enabled=rel(oldpath),previous_enabled_sha256=sha(oldpath),previous_directory=old['installed_directory'],previous_wrapper_sha256=old['wrapper_sha256'],
        installed_directory=directory,installed_files_sha256={k:hashlib.sha256(v).hexdigest() for k,v in files.items()},
        armed_boot=old['expected_boot'],expected_boot=None,TX_expected_boot=fresh['boards']['COM9']['boot_id'],
        bitstream_report=str(bitpath),bitstream_report_sha256=sha(bitpath),overlay_report=str(overlaypath),overlay_report_sha256=sha(overlaypath),
        expected_native_duration_ms=900000,work_directory=WORK,reboots_issued=0,host_launches_RX=False,automatic_TX=False,
        physical_LCD_confirmed=False,true_power_cycle_verified=False,serial_closed=False,profile_selected=False)
    def save():
        write(out/'report.json',r)
        current=dict(status=r['status'],report=rel(out/'report.json'),installed_directory=directory,expected_boot=r['expected_boot'],
            armed_boot=r['armed_boot'],profile_selected=r['profile_selected'],serial_closed=r['serial_closed'],true_power_cycle_verified=False)
        write(ROOT/'results/p57-active.json',current);s=read(ROOT/'TX-SOURCE-STATUS.json');s.update(status=r['status'],authoritative_current_field='p57_current',p57_current=current);write(ROOT/'TX-SOURCE-STATUS.json',s)
    b=None;save();(out/'executed.py').write_bytes(Path(__file__).read_bytes())
    def digest(path):
        b.command('v='+path);q=re.findall(r'^([0-9a-f]{64})\s+\S+\r?$',b.command('sha256sum $v'),re.M)
        if len(q)!=1:raise ValueError('ambiguous SHA')
        return q[0]
    def rf(idle):
        b.command('ir=/sys/bus/iio/devices');n=parse_names(b.command('for n in $ir/iio:device*;do echo __D__$n:$(cat $n/name)__E__;done'))
        b.command('cd '+n['ad9361-phy'])
        if {k:b.value(k) for k in RF_EXPECTED}!=RF_EXPECTED:raise ValueError('RX RF changed')
        b.command('cd '+n['cf-ad9361-lpc'])
        if b.value('buffer/enable')!=('0' if idle else '1'):raise ValueError('unexpected RX DMA state')
        if idle and any(b.value('scan_elements/in_voltage'+str(i)+'_en')!='0' for i in range(4)):raise ValueError('RX scans active')
        if b.value('/proc/sys/kernel/tainted')!='0' or re.search(CRITICAL_KERNEL,b.command('dmesg | tail -n 160')):raise ValueError('kernel error')
    def json_one(command):
        import json
        rows=[json.loads(v) for v in b.command(command).splitlines() if v.startswith('{')]
        if len(rows)!=1:raise ValueError('one native JSON required')
        return rows[0]
    try:
        entry=ROOT/'START-HERE.md';backup=ROOT/('START-HERE-BEFORE-P57-'+stamp+'.md');backup.write_bytes(entry.read_bytes())
        entry.write_text('# 从这里恢复项目工作\n\nP57 正在安装/验证独立 AI 开机配置。先读 results/p57-active.json 及其 report。\n\n'
            '不得根据旧 P56 停止记录判断当前状态。新配置仅新启动时加载已验收硬件，不做热重载。原 P48 配置完整保留。\n\n'
            '原入口：`'+rel(backup)+'`。results/ 被 Git 忽略，读文件系统。\n',encoding='utf-8')
        b=Console('COM8',r,save);b.port=AuditPort(b.port,out);b.shell();b.command('p57_prompt=$PS1');b.command("PS1=''");b.command('stty -echo')
        if b.value('/proc/sys/kernel/random/boot_id')!=r['armed_boot'] or 'Zynq-Tronlong' not in b.command('uname -a'):raise ValueError('RX identity differs')
        rf(True)
        if digest('/etc/rcS.d/S99board')!=old['wrapper_sha256'] or b.value('/etc/board-mode')!='rf':raise ValueError('previous selection differs')
        for name,wanted in old['installed_files_sha256'].items():
            if digest(old['installed_directory']+'/'+name)!=wanted:raise ValueError('previous profile changed '+name)
        for path,key in ((fields['BIT'],'BIT_SHA'),(fields['DTBO'],'DTBO_SHA')):
            if digest(path)!=fields[key]:raise ValueError('cached hardware changed')
        r['resolved_RAM_tmp']=board_ram_tmp(b);temp='/tmp/p35-p57-'+stamp[9:15];b.command('mkdir '+temp)
        for name,data in files.items():
            b.command("PS1='# '");upload(b,temp+'/'+name,data);b.command("PS1=''");b.command('stty -echo')
        b.command('d='+directory);b.command('t='+temp);b.command('mkdir $d')
        for name in files:
            b.command('cp $t/'+name+' $d/'+name);b.command('chmod 755 $d/'+name)
            if digest(directory+'/'+name)!=r['installed_files_sha256'][name]:raise ValueError('installed bytes differ')
        b.command('cp /etc/rcS.d/S99board $d/previous-boot')
        if digest(directory+'/previous-boot')!=old['wrapper_sha256']:raise ValueError('fallback backup changed')
        for name in ('boot','bringup','control','run'):b.command('sh -n $d/'+name)
        b.command('test ! -e $d/disabled');b.command('test ! -e $d/pending');b.command('sync',timeout=20)
        rf(True);b.command('z=/etc/rcS.d/.p57-switch');b.command('test ! -e $z');b.command('cp $d/boot $z');b.command('chmod 755 $z')
        if digest('/etc/rcS.d/.p57-switch')!=r['installed_files_sha256']['boot']:raise ValueError('switch stage differs')
        r['status']='arming_verified_AI_profile';save();b.command('mv $z /etc/rcS.d/S99board');b.command('sync',timeout=20)
        if digest('/etc/rcS.d/S99board')!=r['installed_files_sha256']['boot']:raise ValueError('selected bytes differ')
        r.update(profile_selected=True,status='ordinary_reboot_intent',reboots_issued=1);save();b.port.write(b'reboot\r')
        text=''
        for _ in range(2):
            text+=b.read(35,r'login:\s*$');(out/'boot-console.txt').write_text(text,encoding='utf-8')
            if re.search(r'login:\s*$',text):break
        if not re.search(r'U-Boot|Booting Linux|Linux version',text) or not re.search(r'login:\s*$',text):raise ValueError('fresh kernel/login absent; no reboot retry')
        b.shell();b.command('p57_prompt=$PS1');b.command("PS1=''");b.command('stty -echo')
        boot=b.value('/proc/sys/kernel/random/boot_id');r['expected_boot']=boot;save()
        if boot==r['armed_boot'] or b.value('/run/p43-init-boot')!=boot:raise ValueError('fresh boot marker missing')
        b.command('d='+directory);b.command('w='+WORK);b.command('test ! -e $d/pending');b.command('test ! -e $d/disabled')
        if digest('/etc/rcS.d/S99board')!=r['installed_files_sha256']['boot'] or digest(WORK+'/monitor')!=p['binary_sha256']:raise ValueError('boot or RAM app changed')
        log=b.command('cat /run/p43-boot.log');(out/'startup-log.txt').write_text(log,encoding='utf-8')
        for marker in ('ORIGINAL_BACKUP_VERIFIED','EMPTY_BINDINGS_VERIFIED','PL_ATTEMPT=1','OVERLAY_ATTEMPT=1','MONITOR_LAUNCH','PERSISTENT_MONITOR_READY'):
            if len(re.findall(r'^p43: '+re.escape(marker)+r'(?:\s|\r?$)',log,re.M))!=1:raise ValueError('startup marker '+marker)
        if 'FAILED:' in log:raise ValueError('startup failed')
        r['startup_AI']=json_one('cat $w/data/ai.json');r['startup_progress']=json_one('cat $w/data/progress.json')
        if r['startup_AI']['state']!='CALIBRATION_REQUIRED' or r['startup_AI']['accepted_class']!=-1 or r['startup_AI']['ready'] or r['startup_AI']['boot_id']!=boot:raise ValueError('unsafe initial AI state')
        rf(False);b.command('sleep 2');r['later_AI']=json_one('cat $w/data/ai.json');r['later_progress']=json_one('cat $w/data/progress.json')
        if r['later_progress']['display_updates']<=r['startup_progress']['display_updates'] or r['later_AI']['state']!='CALIBRATION_REQUIRED':raise ValueError('autonomous updates missing')
        r.update(status='passed_P57_warm_boot_autonomous_RX_waits_for_fresh_calibration',RX_running=True,monitor_started_by_board_init=True,
            PL_programming_attempts=1,overlay_apply_attempts=1,fresh_empty_boot_verified=True,persistent_AI_selected=True,
            same_binary_as_P56=True,calibration_provided_by_host=False)
    except Exception as e:r.update(status='failed_or_unconfirmed_P57_boot_do_not_retry_hot',error=repr(e))
    finally:
        if b:
            try:b.command('stty echo');b.command('PS1=$p57_prompt')
            except Exception as e:r['TTY_restore_error']=repr(e)
            b.close()
        r['serial_closed']=True;save();print(out);print(r['status'])
    return int(not r['status'].startswith('passed'))
if __name__=='__main__':raise SystemExit(main())
