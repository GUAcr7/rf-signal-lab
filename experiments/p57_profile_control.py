"""Change only next-boot selection for the independently installed P57 profile."""
import argparse,re
from datetime import datetime,timezone
from pathlib import Path
from p45_checkpoint import ROOT,read,write,sha,rel
from p46_console import Console
from p46_preflight import parse_names
from p35_once_merged_trial import AuditPort
from p36_full_rx_run import RF_EXPECTED,CRITICAL_KERNEL

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--boot',required=True,type=Path);ap.add_argument('--action',choices=('pause','arm','restore-P48'),required=True);ap.add_argument('--review',type=Path);args=ap.parse_args();boot=read(args.boot)
    from p58_boot_contract import validate_boot
    validate_boot(args.boot)
    if args.action=='arm':
        if not args.review:raise ValueError('independent archive review required to arm')
        review=read(args.review)
        if review['status']!='passed_controlled_runtime_AI_full_history_pixels_and_Python_replay' or review.get('boot_report_sha256')!=sha(args.boot):raise ValueError('review must match exact startup')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p57-selection-%Y%m%dT%H%M%SZ');out.mkdir()
    r=dict(status='checking',stages=[],boot=rel(args.boot),boot_sha256=sha(args.boot),action=args.action,
        expected_boot=boot['expected_boot'],RF_operations=False,PL_changes=False,reboots_issued=0,serial_closed=False)
    if args.review:r.update(review=rel(args.review),review_sha256=sha(args.review))
    def save():write(out/'report.json',r)
    def digest(path):
        b.command('v='+path);v=re.findall(r'^([0-9a-f]{64})\s+\S+\r?$',b.command('sha256sum $v'),re.M)
        if len(v)!=1:raise ValueError('ambiguous SHA')
        return v[0]
    b=None;save()
    try:
        b=Console('COM8',r,save);b.port=AuditPort(b.port,out);b.shell();b.command('p57sel_prompt=$PS1');b.command("PS1=''");b.command('stty -echo')
        if b.value('/proc/sys/kernel/random/boot_id')!=boot['expected_boot'] or b.value('/proc/sys/kernel/tainted')!='0':raise ValueError('boot/taint changed')
        b.command('ir=/sys/bus/iio/devices');n=parse_names(b.command('for n in $ir/iio:device*;do echo __D__$n:$(cat $n/name)__E__;done'))
        b.command('cd '+n['ad9361-phy'])
        if {k:b.value(k) for k in RF_EXPECTED}!=RF_EXPECTED:raise ValueError('RF settings changed')
        b.command('cd '+n['cf-ad9361-lpc'])
        if b.value('buffer/enable')!='0' or any(b.value('scan_elements/in_voltage'+str(i)+'_en')!='0' for i in range(4)):raise ValueError('RX not idle')
        if re.search(CRITICAL_KERNEL,b.command('dmesg | tail -n 160')):raise ValueError('kernel error')
        d=boot['installed_directory']
        for name,wanted in boot['installed_files_sha256'].items():
            if digest(d+'/'+name)!=wanted:raise ValueError('installed profile changed '+name)
        b.command('d='+d);b.command('test ! -e $d/pending');b.command('test ! -e $d/disabled')
        current=digest('/etc/rcS.d/S99board')
        if current not in (boot['installed_files_sha256']['boot'],boot['installed_files_sha256']['original']):raise ValueError('unexpected current selection')
        name={'pause':'original','arm':'boot','restore-P48':'previous-boot'}[args.action]
        wanted=boot['previous_wrapper_sha256'] if args.action=='restore-P48' else boot['installed_files_sha256'][name]
        if digest(d+'/'+name)!=wanted:raise ValueError('requested selection changed')
        b.command('z=/etc/rcS.d/.p57-switch');b.command('test ! -e $z');b.command('cp $d/'+name+' $z');b.command('chmod 755 $z')
        if digest('/etc/rcS.d/.p57-switch')!=wanted:raise ValueError('selection staging differs')
        b.command('mv $z /etc/rcS.d/S99board');b.command('sync',timeout=20)
        if digest('/etc/rcS.d/S99board')!=wanted:raise ValueError('selection commit differs')
        r.update(status='passed_idle_P57_next_boot_selection_'+args.action,wrapper_sha256=wanted,RX_idle_verified=True,profile_selected=args.action=='arm')
    except Exception as e:r.update(status='failed_or_unconfirmed_selection',error=repr(e))
    finally:
        if b:
            try:b.command('stty echo');b.command('PS1=$p57sel_prompt')
            except Exception as e:r['TTY_restore_error']=repr(e)
            b.close()
        r['serial_closed']=True;save();print(out);print(r['status'])
    return int(not r['status'].startswith('passed'))
if __name__=='__main__':raise SystemExit(main())
