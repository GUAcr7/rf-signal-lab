"""Isolated receive dashboard build. No board, RF, boot or frozen model edits."""
import json, subprocess
from datetime import datetime, timezone
from pathlib import Path
from p45_checkpoint import ROOT, read, write, sha, rel
from p36_build_rx_full import TOOL, posix
from p56_build_runtime_ai import generate_runtime
from p53_build_live_ai import replace_once as sub

def generate_dashboard():
    frozen,text,core=generate_runtime()
    text=sub(text,'#include "telemetry.h"','#include "telemetry.h"\n#include "dashboard.h"')
    text=sub(text,'            double t1 = now_s();',
        '''            p67_measure(iq,acc,sequence,now_s()-begin);
            if(p67_evidence(argv[arg],"running")){reason="dashboard_evidence_failed";progress_error=1;break;}
            double t1 = now_s();''')
    text=sub(text,'                draw(acc, &m, 2, 8192,','                p67_draw(acc, &m, 2, 8192,')
    text=sub(text,'    if (map && updates) {',
        '''    if(updates && p67_evidence(argv[arg],status==0 ? "finished" : clean_stop ? "stopped" : "failed")){
        status=1;reason="dashboard_final_evidence_failed";
    }
    if (map && updates) {''')
    text=text.replace('\\"display_revision\\":\\"p56\\"','\\"display_revision\\":\\"p67\\"')
    return frozen,text,core

def main():
    frozen,text,core=generate_dashboard()
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p67-build-%Y%m%dT%H%M%SZ');out.mkdir()
    bundle=out/'bundle';bundle.mkdir()
    (bundle/'monitor.c').write_text(text,encoding='utf-8');(bundle/'ai_impl.h').write_text(core,encoding='utf-8')
    for key,name in (('C','trained_cnn_infer.c'),('header','trained_model.h'),('taps','rf_frontend.h')):
        (bundle/name).write_bytes((ROOT/frozen['frozen_inputs'][key]['path']).read_bytes())
    for name in ('runtime_policy.h','telemetry.h'):
        (bundle/name).write_bytes((ROOT/'embedded/arm_live_panel_p56'/name).read_bytes())
    (bundle/'dashboard.h').write_bytes((ROOT/'embedded/arm_live_panel_p67/dashboard.h').read_bytes())
    r=dict(status='building',board_operations=False,stages=[],frozen='results/p52-export-20261024T043113Z/report.json')
    def run(label,cmd,timeout=120):
        q=subprocess.run([str(v) for v in cmd],capture_output=True,timeout=timeout)
        (out/(label+'.stdout')).write_bytes(q.stdout);(out/(label+'.stderr')).write_bytes(q.stderr)
        r['stages'].append(dict(label=label,exit_code=q.returncode));write(out/'report.json',r)
        if q.returncode:raise ValueError(label+' failed')
        return q.stdout.decode()
    try:
        flags=['-std=c11','-O2','-Wall','-Wextra','-Werror','-fno-fast-math','-ffp-contract=off','-pthread']
        host=out/'monitor-host';arm=out/'monitor-arm'
        run('host-build',['wsl.exe','--exec','gcc',*flags,'-I',posix(ROOT/'embedded/vendor/libiio-v0.24'),posix(bundle/'monitor.c'),'-o',posix(host),'-ldl','-lrt','-lm'])
        run('ARM-build',['wsl.exe','--exec',posix(TOOL/'arm-linux-gnueabihf-gcc'),*flags,'-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard','-marm','-I',posix(ROOT/'embedded/vendor/libiio-v0.24'),posix(bundle/'monitor.c'),'-o',posix(arm),'-ldl','-lrt','-lm'])
        elf=run('ARM-ELF',['wsl.exe','--exec',posix(TOOL/'arm-linux-gnueabihf-readelf'),'-h','-A','-l','-V',posix(arm)])
        if 'ELF32' not in elf or 'VFP registers' not in elf or '/lib/ld-linux-armhf.so.3' not in elf:raise ValueError('ARM ABI differs')
        run('mock-build',['wsl.exe','--exec','gcc',*flags,'-shared','-fPIC','-I',posix(ROOT/'embedded/vendor/libiio-v0.24'),posix(ROOT/'tests/native/mock_latest_panel_p39.c'),'-o',posix(out/'libiio.so.0'),'-ldl','-lm'])
        for fault in ('','version','config','format','step','end','sample_size','create','short','after_config','cancel','join_hang'):
            folder=out/('mock-'+(fault or 'good'));log=out/('mock-'+(fault or 'good')+'.release')
            q=subprocess.run(['wsl.exe','--exec','env','LD_LIBRARY_PATH='+posix(out),'P36_MOCK_FAULT='+fault,'P36_MOCK_LOG='+posix(log),posix(host),'--analyse-only',posix(folder),'600','100'],capture_output=True,timeout=15)
            (out/('mock-'+(fault or 'good')+'.stdout')).write_bytes(q.stdout)
            if fault=='join_hang':ok=q.returncode==3 and b'"cleanup_unconfirmed":true' in q.stdout and not log.exists()
            else:
                s=read(folder/'summary.json');ok=(q.returncode==0 if fault in ('','cancel') else q.returncode!=0) and s['buffer_released'] and s['context_released'] and not s['cleanup_unconfirmed']
                if not fault:
                    d=read(folder/'dashboard.json');a=read(folder/'ai.json')
                    ok=ok and s['display_revision']=='p67' and d['source_block_sequence']==a['source_block_sequence']==s['last_display_sequence'] and d['state']=='finished' and d['AI_state']=='STOPPED' and a['state']=='STOPPED'
            r['stages'].append(dict(label='mock-'+(fault or 'good'),exit_code=q.returncode,gate_passed=bool(ok)));write(out/'report.json',r)
            if not ok:raise ValueError('lifecycle failed: '+fault)
        inputs=[Path(__file__),ROOT/'embedded/arm_live_panel_p67/dashboard.h',*bundle.iterdir()]
        r.update(status='passed_P67_build_12_lifecycle_cases_not_deployed',binary=rel(arm),binary_sha256=sha(arm),host=rel(host),inputs_sha256={rel(p):sha(p) for p in inputs})
    except Exception as e:r.update(status='failed_not_deployed',error=repr(e))
    write(out/'report.json',r);print(out);print(r['status']);return int(not r['status'].startswith('passed'))
if __name__=='__main__':raise SystemExit(main())
