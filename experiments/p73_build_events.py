"""Build bounded same-update event diagnostics from the exact tested P69 bundle."""
import subprocess
from datetime import datetime,timezone
from pathlib import Path
from p45_checkpoint import ROOT,read,write,sha,rel
from p36_build_rx_full import TOOL,posix
from p53_build_live_ai import replace_once as sub


def main():
    baseline=ROOT/'results/p69-build-20261026T024734Z/report.json';b=read(baseline)
    for p,h in b['inputs_sha256'].items():
        if sha(ROOT/p)!=h:raise ValueError('P69 input changed '+p)
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p73-build-%Y%m%dT%H%M%SZ');out.mkdir()
    bundle=out/'bundle';bundle.mkdir()
    old=(ROOT/b['binary']).parent/'bundle'
    for p in old.iterdir():(bundle/p.name).write_bytes(p.read_bytes())
    source=ROOT/'embedded/arm_live_panel_p73/event_capture.h'
    (bundle/source.name).write_bytes(source.read_bytes())
    text=(old/'monitor.c').read_text(encoding='utf-8')
    text=sub(text,'#include "measurements.h"','#include "measurements.h"\n#include "event_capture.h"')
    text=sub(text,'            double t2 = now_s();','            if(p73_event(argv[arg],shown)){reason="event_capture_failed";progress_error=1;break;}\n            double t2 = now_s();')
    text=text.replace('\\"display_revision\\":\\"p69\\"','\\"display_revision\\":\\"p73\\"')
    (bundle/'monitor.c').write_text(text,encoding='utf-8')
    r=dict(status='building',baseline=rel(baseline),baseline_sha256=sha(baseline),
        frozen=b['frozen'],board_operations=False,instrumentation_only=True,
        frozen_policy_SHA=sha(bundle/'runtime_policy.h'),frozen_CNN_core_SHA=sha(bundle/'ai_impl.h'),stages=[])
    def run(label,cmd):
        q=subprocess.run([str(v) for v in cmd],capture_output=True,timeout=120)
        (out/(label+'.stdout')).write_bytes(q.stdout);(out/(label+'.stderr')).write_bytes(q.stderr)
        r['stages'].append(dict(label=label,exit_code=q.returncode));write(out/'report.json',r)
        if q.returncode:raise ValueError(label+' failed')
        return q.stdout.decode(errors='replace')
    flags=['-std=c11','-O2','-Wall','-Wextra','-Werror','-fno-fast-math','-ffp-contract=off','-pthread']
    try:
        for label,compiler in [('host-build','gcc'),('ARM-build',posix(TOOL/'arm-linux-gnueabihf-gcc'))]:
            target=out/('monitor-host' if label=='host-build' else 'monitor-arm')
            cpu=[] if label=='host-build' else ['-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard','-marm']
            run(label,['wsl.exe','--exec',compiler,*flags,*cpu,'-I',posix(ROOT/'embedded/vendor/libiio-v0.24'),posix(bundle/'monitor.c'),'-o',posix(target),'-ldl','-lrt','-lm'])
        for name in ('runtime_policy.h','ai_impl.h','trained_cnn_infer.c','trained_model.h','rf_frontend.h'):
            if sha(bundle/name)!=sha(old/name):raise ValueError('frozen algorithm changed '+name)
        r.update(status='built_P73_event_diagnostic_offline_tests_pending',binary=rel(out/'monitor-arm'),binary_sha256=sha(out/'monitor-arm'),
                 host=rel(out/'monitor-host'),inputs_sha256={rel(p):sha(p) for p in [Path(__file__),source,*bundle.iterdir()]})
    except Exception as e:r.update(status='failed_P73_not_deployed',error=repr(e))
    write(out/'report.json',r);print(out);print(r['status']);return int(r['status'].startswith('failed'))


if __name__=='__main__':raise SystemExit(main())
