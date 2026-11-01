"""Pin and test persistent shells before target startup installation."""
from datetime import datetime,timezone
import hashlib,json,subprocess,sys
from pathlib import Path
import xml.etree.ElementTree as ET
from p32_session import ROOT
from p36_build_rx_full import posix
from p43_boot_templates import render

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p43-preparation-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    paths=['board/boot/S99board','board/boot/p41-monitor-once.sh.in','board/boot/p43-persistent-guard.sh.in',
        'board/boot/p43-monitor-control.sh.in','experiments/p43_boot_templates.py','experiments/p43_prepare_startup.py','tests/test_p43_boot_shell.py']
    hashes={s:sha(ROOT/s) for s in paths};r=dict(status='testing',board_operations=False,inputs_sha256=hashes)
    for s in paths:
        target=out/'inputs'/s;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((ROOT/s).read_bytes())
    def save():(out/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    save()
    try:
        xml=out/'tests.xml';result=subprocess.run([sys.executable,'-m','pytest','tests/test_p43_boot_shell.py','-q','--junitxml='+str(xml)],cwd=ROOT,capture_output=True,timeout=150)
        (out/'tests.stdout').write_bytes(result.stdout);(out/'tests.stderr').write_bytes(result.stderr)
        cases=list(ET.parse(xml).getroot().iter('testcase'))
        if result.returncode or len(cases)!=13 or any(list(c.iter(t)) for c in cases for t in ('failure','error','skipped')):raise ValueError('shell tests failed')
        files=render('/etc/p43-20261022T030000Z','00000000-0000-0000-0000-000000000001','0'*64,
            '/lib/firmware/p35-ttl-20261021T090121Z.bin','1'*64,'/lib/firmware/p35-merged-20261021T090121Z.dtbo','2'*64)
        for name in ('boot','bringup','control','run'):
            path=out/(name+'.sh');path.write_bytes(files[name])
            result=subprocess.run(['wsl.exe','--exec','sh','-n',posix(path)],capture_output=True,timeout=15)
            if result.returncode:raise ValueError('shell syntax failed '+name)
        if any(sha(ROOT/s)!=v for s,v in hashes.items()):raise ValueError('tested inputs changed')
        r.update(status='passed_persistent_shell_and_stop_gates_not_hardware_boot',test_count=13,
            test_xml=str(xml),test_xml_sha256=sha(xml),input_hashes_unchanged=True)
    except Exception as e:r.update(status='failed',error=repr(e))
    save();print(out);print(r['status']);return 0 if r['status'].startswith('passed_') else 1
if __name__=='__main__':raise SystemExit(main())
