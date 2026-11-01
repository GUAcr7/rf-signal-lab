"""Freeze/test P57 startup bytes before installation; no board operations."""
import subprocess,sys,xml.etree.ElementTree as ET
from datetime import datetime,timezone
from pathlib import Path
from p45_checkpoint import ROOT,read,write,sha,rel
from p36_build_rx_full import posix
from p57_boot_templates import render

def main():
    accepted=ROOT/'results/p56-review-20261024T091539Z/report.json';a=read(accepted)
    if a['status']!='passed_controlled_runtime_AI_full_history_pixels_and_Python_replay' or not a['ten_minute_duration_verified']:raise ValueError('accepted P56 required')
    t=read(ROOT/a['trial']);b=read(ROOT/t['build']);binary=ROOT/b['binary']
    for name,digest in b['inputs_sha256'].items():
        if sha(ROOT/name)!=digest:raise ValueError('candidate build changed '+name)
    if sha(binary)!=b['binary_sha256']:raise ValueError('accepted ARM binary changed')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p57-preparation-%Y%m%dT%H%M%SZ');out.mkdir()
    r=dict(status='testing',board_operations=False,accepted_review=rel(accepted),accepted_review_sha256=sha(accepted),
        build=t['build'],build_sha256=sha(ROOT/t['build']),binary=rel(binary),binary_sha256=sha(binary))
    try:
        xml=out/'tests.xml';q=subprocess.run([sys.executable,'-m','pytest','tests/test_p57_boot_shell.py','-q','--junitxml='+str(xml)],cwd=ROOT,capture_output=True,timeout=180)
        (out/'tests.stdout').write_bytes(q.stdout);(out/'tests.stderr').write_bytes(q.stderr)
        cases=list(ET.parse(xml).getroot().iter('testcase'))
        if q.returncode or len(cases)!=15 or any(list(c.iter(k)) for c in cases for k in ('error','failure','skipped')):raise ValueError('startup/control tests failed')
        files=render('/etc/p43-20261024T100000Z','00000000-0000-0000-0000-000000000001',sha(binary),
            '/lib/firmware/p35-ttl-20261021T090121Z.bin','1'*64,'/lib/firmware/p35-merged-20261021T090121Z.dtbo','2'*64)
        for name in ('boot','bringup','control','run'):
            p=out/(name+'.sh');p.write_bytes(files[name]);q=subprocess.run(['wsl.exe','--exec','sh','-n',posix(p)],capture_output=True,timeout=15)
            if q.returncode:raise ValueError('shell syntax '+name)
        paths=['experiments/p57_boot_templates.py','experiments/p57_prepare_boot.py','tests/test_p57_boot_shell.py',
            'board/boot/S99board','board/boot/p41-monitor-once.sh.in','board/boot/p43-persistent-guard.sh.in',
            'board/boot/p43-monitor-control.sh.in','experiments/p43_boot_templates.py']
        r.update(status='passed_P57_startup_control_15_offline_cases_not_boot_test',test_count=15,
            tests_xml=rel(xml),tests_xml_sha256=sha(xml),inputs_sha256={v:sha(ROOT/v) for v in paths})
    except Exception as e:r.update(status='failed_not_deployed',error=repr(e))
    write(out/'report.json',r);print(out);print(r['status']);return int(not r['status'].startswith('passed'))
if __name__=='__main__':raise SystemExit(main())
