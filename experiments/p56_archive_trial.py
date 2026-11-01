"""Pack stopped P56 evidence in RAM, then archive using the reviewed P36 reader."""
import argparse,json,re,subprocess,sys,tarfile,io
from datetime import datetime,timezone
from pathlib import Path
from p45_checkpoint import ROOT,read,write,sha,rel
from p46_console import Console
from p46_preflight import parse_names
from p35_once_merged_trial import AuditPort
from p52_ram import board_ram_tmp
from p37_review_archives import archive_bytes

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--trial',required=True,type=Path);args=ap.parse_args()
    trial=read(args.trial)
    if trial['status']!='captured_runtime_AI_pending_byte_archives_and_independent_review' or not trial['RX_idle_verified'] or not trial['TX_idle_verified']:raise ValueError('stopped trial required')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p56-archive-%Y%m%dT%H%M%SZ');out.mkdir()
    r=dict(status='packing',stages=[],trial=rel(args.trial),trial_sha256=sha(args.trial),serial_closed=False,expected_boot=trial['expected_boot'])
    def save():write(out/'report.json',r)
    b=None
    def digest(path):
        b.command('v='+path);a=re.findall(r'^([0-9a-f]{64})\s+\S+\r?$',b.command('sha256sum $v'),re.M)
        if len(a)!=1:raise ValueError('ambiguous digest')
        return a[0]
    def count(path):
        b.command('v='+path);a=re.findall(r'^__N__(\d+)__E__\r?$',b.command('echo __N__$(wc -c <$v)__E__'),re.M)
        if len(a)!=1:raise ValueError('ambiguous size')
        return int(a[0])
    save()
    try:
        b=Console('COM8',r,save);b.port=AuditPort(b.port,out);b.shell();b.command('p56_arc_prompt=$PS1');b.command("PS1=''");b.command('stty -echo')
        if b.value('/proc/sys/kernel/random/boot_id')!=trial['expected_boot'] or b.value('/proc/sys/kernel/tainted')!='0':raise ValueError('identity changed')
        b.command('ir=/sys/bus/iio/devices');n=parse_names(b.command('for n in $ir/iio:device*;do echo __D__$n:$(cat $n/name)__E__;done'))
        b.command('cd '+n['cf-ad9361-lpc'])
        if b.value('buffer/enable')!='0' or any(b.value('scan_elements/in_voltage'+str(i)+'_en')!='0' for i in range(4)):raise ValueError('RX still active')
        r['RAM_tmp']=board_ram_tmp(b);b.command('s='+trial['stage']);b.command('cd '+trial['directory']);b.command('test ! -e $s/e.tar')
        b.command('tar -cf $s/e.tar ai-history.jsonl shot-* fb.raw',timeout=20)
        b.command('gzip -1 -c $s/e.tar >$s/e.tar.gz',timeout=20);b.command('gzip -t $s/e.tar.gz')
        r['contract']=dict(remote=trial['stage']+'/e.tar.gz',expected_bytes=count(trial['stage']+'/e.tar.gz'),
            expected_sha256=digest(trial['stage']+'/e.tar.gz'),raw_bytes=count(trial['stage']+'/e.tar'),raw_sha256=digest(trial['stage']+'/e.tar'))
        r['status']='packed_pending_host_archive';save()
    except Exception as e:r.update(status='failed_archive',error=repr(e))
    finally:
        if b:
            try:b.command('stty echo');b.command('PS1=$p56_arc_prompt')
            except Exception as e:r['TTY_restore_error']=repr(e)
            b.close()
        r['serial_closed']=True;save()
    if r['status']=='packed_pending_host_archive':
        try:
            command=[sys.executable,str(ROOT/'experiments/p56_retrieve_file.py'),'--expected-boot',trial['expected_boot']]
            for k,v in r['contract'].items():command.extend(['--'+k.replace('_','-'),str(v)])
            q=subprocess.run(command,capture_output=True,timeout=600);(out/'reader.stdout').write_bytes(q.stdout);(out/'reader.stderr').write_bytes(q.stderr)
            reports=[Path(s.strip())/'report.json' for s in q.stdout.decode().splitlines() if Path(s.strip()).is_absolute() and (Path(s.strip())/'report.json').is_file()]
            if q.returncode or len(reports)!=1:raise ValueError('reader incomplete')
            r.update(archive=rel(reports[0]),archive_sha256=sha(reports[0]));_,raw=archive_bytes(reports[0])
            files={v['original_name']:v for v in trial['archives'].values()}
            with tarfile.open(fileobj=io.BytesIO(raw),mode='r:') as tf:
                members=tf.getmembers()
                if len(members)!=len(files) or len(members)>24 or len({v.name for v in members})!=len(members):raise ValueError('tar membership differs')
                for m in members:
                    if not m.isfile() or m.name not in files or m.size!=files[m.name]['raw_bytes']:raise ValueError('unexpected evidence member')
                    data=tf.extractfile(m).read();path=out/m.name;path.write_bytes(data)
                    if sha(path)!=files[m.name]['raw_sha256']:raise ValueError('member SHA differs')
            r.update(status='passed_P56_full_history_and_IQ_pixels_byte_archived',files_sha256={name:sha(out/name) for name in files})
        except Exception as e:r.update(status='failed_archive',error=repr(e))
        save()
    print(out);print(r['status']);return int(not r['status'].startswith('passed'))
if __name__=='__main__':raise SystemExit(main())
