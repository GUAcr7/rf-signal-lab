"""Pin and execute the real startup shell tests before any target boot change."""
from datetime import datetime,timezone
import hashlib,json,subprocess,sys
from pathlib import Path
import xml.etree.ElementTree as ET
from p32_session import ROOT
from p36_build_rx_full import posix
from p41_boot_templates import render_runtime,render_boot


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p41-preparation-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    paths=['board/boot/p41-monitor-once.sh.in','board/boot/p35-once-hold.sh.in','board/boot/S99board',
        'experiments/p41_boot_templates.py','tests/test_p41_boot_shell.py','experiments/p41_prepare_autonomous.py']
    hashes={p:sha(ROOT/p) for p in paths}
    for path in paths:
        target=out/'inputs'/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((ROOT/path).read_bytes())
    r=dict(status='testing',inputs_sha256=hashes,board_operations=False,test_scope='actual POSIX shell control flow on remapped temporary filesystem; no hardware model proof')
    def save():(out/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    save()
    try:
        xml=out/'tests.xml'
        result=subprocess.run([sys.executable,'-m','pytest','tests/test_p41_boot_shell.py','-q','--junitxml='+str(xml)],cwd=ROOT,capture_output=True,timeout=120)
        (out/'tests.stdout').write_bytes(result.stdout);(out/'tests.stderr').write_bytes(result.stderr)
        cases=list(ET.parse(xml).getroot().iter('testcase'))
        if result.returncode or len(cases)!=8 or any(list(c.iter(tag)) for c in cases for tag in ('failure','error','skipped')):raise ValueError('actual shell tests failed')
        runtime=render_runtime('/etc/p41-20261021T160000Z/monitor','0'*64,
            '/lib/firmware/p35-ttl-20261021T090121Z.bin','1'*64,
            '/lib/firmware/p35-merged-20261021T090121Z.dtbo','2'*64,'3'*64,
            '00000000-0000-0000-0000-000000000001','/tmp/p35-p39-160000')
        boot=render_boot('/etc/p35-guard-20261021T160000Z','3'*64,
            '00000000-0000-0000-0000-000000000001','/etc/p41-20261021T160000Z/bringup',hashlib.sha256(runtime).hexdigest())
        for name,data in [('runtime.sh',runtime),('boot.sh',boot)]:
            target=out/name;target.write_bytes(data)
            result=subprocess.run(['wsl.exe','--exec','sh','-n',posix(target)],capture_output=True,timeout=15)
            if result.returncode:raise ValueError('target shell syntax failed')
        if any(sha(ROOT/p)!=digest for p,digest in hashes.items()):raise ValueError('tested sources changed')
        r.update(status='passed_actual_shell_gates_and_template_syntax_not_board_boot',test_count=8,
            test_xml=str(xml),test_xml_sha256=sha(xml),input_hashes_unchanged=True)
    except Exception as exc:r.update(status='failed',error=repr(exc))
    save();print(out);print(r['status'])
    return 0 if r['status'].startswith('passed_') else 1


if __name__=='__main__':raise SystemExit(main())
