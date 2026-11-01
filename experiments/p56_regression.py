"""Targeted frozen-frontend/model and retained P48 display regressions, PC only."""
import subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
from p45_checkpoint import ROOT,read,write,sha,rel

def main():
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p56-regression-%Y%m%dT%H%M%SZ');out.mkdir()
    frozen=ROOT/'results/p52-export-20261024T043113Z/report.json';f=read(frozen)
    files=['tests/test_rf_ai_input.py','tests/test_rf_ai_calibration.py','tests/test_cnn_quantization.py',
        'tests/test_real_rf_ram_gate.py','tests/test_real_rf_learning.py','tests/test_real_rf_arm_evidence.py','tests/test_native_display_p48.py']
    r=dict(status='running',board_operations=False,frozen=rel(frozen),frozen_sha256=sha(frozen),tests=files)
    write(out/'report.json',r)
    try:
        for v in f['frozen_inputs'].values():
            if sha(ROOT/v['path'])!=v['sha256']:raise ValueError('frozen file changed '+v['path'])
        q=subprocess.run([sys.executable,'-m','pytest','-q',*files],cwd=ROOT,capture_output=True,timeout=240)
        (out/'pytest.stdout').write_bytes(q.stdout);(out/'pytest.stderr').write_bytes(q.stderr)
        r.update(status='passed_targeted_frozen_AI_and_P48_display_regressions' if q.returncode==0 else 'failed_targeted_regressions',exit_code=q.returncode,
            result_tail=q.stdout.decode(errors='replace').splitlines()[-4:])
    except Exception as e:r.update(status='failed_targeted_regressions',error=repr(e))
    write(out/'report.json',r);print(out);print(r['status']);return int(not r['status'].startswith('passed'))
if __name__=='__main__':raise SystemExit(main())
