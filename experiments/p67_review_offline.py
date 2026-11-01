"""Archive actual numerical/renderer tests and regress frozen AI policy."""
import argparse,json,shutil,subprocess
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
from PIL import Image
from p45_checkpoint import ROOT,read,write,sha,rel
from p36_build_rx_full import posix

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--build',required=True,type=Path)
    ap.add_argument('--pytest-root',required=True,type=Path);a=ap.parse_args()
    b=read(a.build)
    if b['status']!='passed_P67_build_12_lifecycle_cases_not_deployed':raise ValueError('build required')
    for p,h in b['inputs_sha256'].items():
        if sha(ROOT/p)!=h:raise ValueError('changed build input '+p)
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p67-offline-%Y%m%dT%H%M%SZ');out.mkdir()
    r=dict(status='reviewing',build=rel(a.build),build_sha256=sha(a.build),board_operations=False,
        scope='synthetic measurement/renderer tests and previously exposed RF policy regression; not new AI accuracy')
    try:
        log=ROOT/'results/p67-dashboard-tests-20261026.xml'
        import xml.etree.ElementTree as ET
        suite=ET.parse(log).getroot().find('testsuite')
        if suite is None or suite.get('tests')!='8' or suite.get('failures')!='0' or suite.get('errors')!='0':raise ValueError('8 passing numerical tests required')
        shutil.copyfile(log,out/log.name)
        cases=[]
        for src in sorted(a.pytest_root.glob('test_*/output/render.raw')):
            case=out/src.parent.parent.name;case.mkdir()
            for name in ('render.raw','dashboard.json','power.bin'):
                shutil.copyfile(src.parent/name,case/name)
            shutil.copyfile(src.parent.parent/'iq.bin',case/'iq.bin')
            cases.append(rel(case))
            if 'waterfall_ring' in case.name:
                pixels=np.fromfile(case/'render.raw',dtype='<u4').reshape(480,800)
                rgb=np.stack(((pixels>>16)&255,(pixels>>8)&255,pixels&255),axis=-1).astype('uint8')
                Image.fromarray(rgb).save(out/'synthetic-preview-NOT-BOARD.png')
        if len(cases)!=8:raise ValueError('eight renderer fixtures required')
        r['renderer_cases']=cases
        bundle=(ROOT/b['binary']).parent/'bundle'
        (out/'test_monitor.c').write_text((bundle/'monitor.c').read_text().replace('int main(int argc, char **argv) {','int candidate_main(int argc, char **argv) {'),encoding='utf-8')
        flags=['-std=c11','-O2','-Wall','-Wextra','-Werror','-fno-fast-math','-ffp-contract=off','-pthread']
        cmd=['wsl.exe','--exec','gcc',*flags,'-I',posix(out),'-I',posix(bundle),'-I',posix(ROOT/'embedded/vendor/libiio-v0.24'),posix(ROOT/'tests/native/p56_policy_harness.c'),'-o',posix(out/'policy-host'),'-lm','-ldl','-lrt']
        q=subprocess.run(cmd,capture_output=True,timeout=120);(out/'policy-build.stderr').write_bytes(q.stderr)
        if q.returncode:raise ValueError('policy compile failed')
        parent=ROOT/'results/p56-policy-20261024T085402Z';gold=read(parent/'report.json')
        q=subprocess.run(['wsl.exe','--exec',posix(out/'policy-host'),posix(parent/'steps.txt'),posix(out/'control')],capture_output=True,timeout=120)
        (out/'policy.stdout').write_bytes(q.stdout);(out/'policy.stderr').write_bytes(q.stderr)
        if q.returncode:raise ValueError('policy execution failed')
        rows=[json.loads(line) for line in q.stdout.decode().splitlines() if line.startswith('{')]
        if rows!=gold['rows']:raise ValueError('frozen policy/full frontend output changed')
        r.update(status='passed_P67_8_renderer_numeric_tests_19_policy_steps',policy_rows=len(rows),
            policy_reference=rel(parent/'report.json'),policy_reference_sha256=sha(parent/'report.json'),
            test_source_sha256=sha(ROOT/'tests/test_dashboard_p67.py'))
    except Exception as e:r.update(status='failed_offline_review',error=repr(e))
    r['files_sha256']={rel(p):sha(p) for p in out.rglob('*') if p.is_file() and p.name!='report.json'}
    write(out/'report.json',r);print(out);print(r['status']);return int(not r['status'].startswith('passed'))
if __name__=='__main__':raise SystemExit(main())
