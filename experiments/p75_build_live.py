"""Derive isolated RAM candidate from tested P69; retain its lifecycle tests."""
from datetime import datetime,timezone
from pathlib import Path
from p45_checkpoint import ROOT,read,write,sha,rel
from p53_build_live_ai import replace_once as sub


def generate():
    parent=ROOT/'experiments/p69_build_metrics.py'
    baseline=read(ROOT/'results/p69-build-20261026T024734Z/report.json')
    if sha(parent)!=baseline['inputs_sha256'][rel(parent)]:raise ValueError('tested P69 builder changed')
    final=read(ROOT/'results/p74-final-20261026T095803Z/manifest.json')['files']
    for name in ('embedded/arm_live_panel_p74/phase_pool.h','embedded/arm_live_panel_p73/event_capture.h'):
        if sha(ROOT/name)!=final[name]['sha256']:raise ValueError('reviewed header changed')
    text=parent.read_text(encoding='utf-8')
    text=sub(text,'    frozen,text,core=generate_metrics()', '''    frozen,text,core=generate_metrics()
    core=sub(core,'#undef main','#undef main\\n#include "phase_pool.h"')
    core=sub(core,'if(infer(quantized))','if(p74_infer(quantized))')
    text=sub(text,'#include "measurements.h"','#include "measurements.h"\\n#include "event_capture.h"')
    text=sub(text,'            double t2 = now_s();','            if(p73_event(argv[arg],shown)){reason="event_capture_failed";progress_error=1;break;}\\n            double t2 = now_s();')
    text=text.replace('display_revision\\\\\\":\\\\\\"p69','display_revision\\\\\\":\\\\\\"p75')
''')
    # Replace the generated monitor revision in the builder's escaped literals.
    text=text.replace("s['display_revision']=='p69'","s['display_revision']=='p75'")
    text=sub(text,'    for p in sources:(bundle/p.name).write_bytes(p.read_bytes())',
        '    sources += [ROOT/"embedded/arm_live_panel_p74/phase_pool.h",ROOT/"embedded/arm_live_panel_p73/event_capture.h"]\n    for p in sources:(bundle/p.name).write_bytes(p.read_bytes())')
    text=text.replace("strftime('p69-build-","strftime('p75-build-")
    text=text.replace('passed_P69_build_12_lifecycle_cases_not_deployed','passed_P75_phase_candidate_build_lifecycle12_not_deployed')
    text=sub(text,"        parents=['experiments/p67_build_dashboard.py'",'''        # Separate full packed-IQ CLI for Python/native/ARM end-to-end parity.
        raw=(ROOT/frozen['frozen_inputs']['frontend']['path']).read_text(encoding='utf-8')
        raw=sub(raw,'#undef main','#undef main\\n#include "phase_pool.h"')
        raw=sub(raw,'if(infer(quantized))','if(p74_infer(quantized))')
        (bundle/'phase_raw.c').write_text(raw,encoding='utf-8')
        run('raw-host-build',['wsl.exe','--exec','gcc',*flags,posix(bundle/'phase_raw.c'),'-o',posix(out/'phase-raw-host'),'-lm'])
        run('raw-ARM-build',['wsl.exe','--exec',posix(TOOL/'arm-linux-gnueabihf-gcc'),*flags,'-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard','-marm',posix(bundle/'phase_raw.c'),'-o',posix(out/'phase-raw-ARM'),'-lm'])
        r.update(raw_host=rel(out/'phase-raw-host'),raw_host_sha256=sha(out/'phase-raw-host'),raw_ARM=rel(out/'phase-raw-ARM'),raw_ARM_sha256=sha(out/'phase-raw-ARM'),candidate='P74 fixed eight phases; same original weights and 3/3 policy')
        parents=['experiments/p67_build_dashboard.py' ''')
    return text,parent


if __name__=='__main__':
    code,parent=generate()
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p75-build-code-%Y%m%dT%H%M%SZ');out.mkdir()
    path=out/'executed-build.py';path.write_text(code,encoding='utf-8')
    write(out/'report.json',dict(parent=rel(parent),parent_sha256=sha(parent),code=rel(path),code_sha256=sha(path),entry_sha256=sha(Path(__file__))))
    exec(compile(code,str(path),'exec'),dict(__name__='__main__',__file__=str(path)))
