"""Isolated P56: boot-bound calibration and explicit abstention; frozen P52 math."""
import json,subprocess
from datetime import datetime,timezone
from pathlib import Path
from p45_checkpoint import ROOT,read,write,sha,rel
from p36_build_rx_full import TOOL,posix
from p53_build_live_ai import generate,replace_once as sub


def generate_runtime():
    frozen=read(ROOT/'results/p52-export-20261024T043113Z/report.json')
    for v in frozen['frozen_inputs'].values():
        if sha(ROOT/v['path'])!=v['sha256']:raise ValueError('frozen input changed: '+v['path'])
    text,core=generate((ROOT/'embedded/arm_live_panel_p48/arm_live_panel_p48.c').read_text(),
        (ROOT/frozen['frozen_inputs']['frontend']['path']).read_text(),0,frozen['selected_mode'])
    core=sub(core,'static int ai_predictions[3];','static double p56_frame_powers[3];\nstatic int ai_predictions[3];')
    core=sub(core,'        if(infer(quantized)) return 2;', '''        double mi=0,mq=0,p=0;
        for(int j=0;j<1024;j++){mi+=original[2*j];mq+=original[2*j+1];}
        mi/=1024;mq/=1024;
        for(int j=0;j<1024;j++){double i=original[2*j]-mi,q=original[2*j+1]-mq;p+=i*i+q*q;}
        p56_frame_powers[frame]=p/1024;
        if(infer(quantized)){ai_predictions[frame]=-1;memset(ai_logits[frame],0,sizeof ai_logits[frame]);continue;}''')
    start=text.index('static int save_ai(');end=text.index('int main(int argc, char **argv) {',start)
    text=text[:start]+'#include "runtime_policy.h"\n#include "telemetry.h"\n'+text[end:]
    text=sub(text,'number(argv[arg+1], 100, 10000, &duration_ms)','number(argv[arg+1], 100, 1200000, &duration_ms)')
    text=text.replace('DURATION_MS_100_10000','DURATION_MS_100_1200000')
    text=sub(text,'    if (mkdir(argv[arg], 0700))','    if(p56_initialize())return 2;\n    p56_begin=now_s();\n    if (mkdir(argv[arg], 0700))')
    text=sub(text,'            if(infer_block(AI_IF_HZ,!strcmp(AI_MODE,"int8"),0)){reason="AI_input_invalid";progress_error=1;break;}',
        '            if(p56_step(shown)){reason="AI_policy_failed";progress_error=1;break;}')
    text=text.replace('save_ai(argv[arg],sequence)','p56_evidence(argv[arg],sequence)').replace('ai_line();','p56_line();')
    text=sub(text,'            double t2 = now_s();','            if(p56_shot(argv[arg],shown,!analyse_only)){reason="AI_shot_failed";progress_error=1;break;}\n            double t2 = now_s();')
    text=sub(text,'    if (map && updates) {','''    p56_state=P56_STOPPED;p56_class=-1;
    if(updates && p56_evidence(argv[arg],s.consumed_sequence)){status=1;reason="AI_final_evidence_failed";}
    if(p56_history && fclose(p56_history)){status=1;reason="AI_history_close_failed";}
    if (map && updates) {''')
    text=text.replace('\\"display_revision\\":\\"p53\\"','\\"display_revision\\":\\"p56\\"')
    macros='static double ai_if_hz;\n#define AI_IF_HZ ai_if_hz\n#define AI_MODE "int8"\n#define AI_MODEL_SHA "'+frozen['frozen_inputs']['model']['sha256']+'"\n'
    return frozen,text,macros+core


def main():
    frozen,text,core=generate_runtime()
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p56-build-%Y%m%dT%H%M%SZ');out.mkdir()
    bundle=out/'bundle';bundle.mkdir()
    (bundle/'monitor.c').write_text(text,encoding='utf-8');(bundle/'ai_impl.h').write_text(core,encoding='utf-8')
    for key,name in (('C','trained_cnn_infer.c'),('header','trained_model.h'),('taps','rf_frontend.h')):
        (bundle/name).write_bytes((ROOT/frozen['frozen_inputs'][key]['path']).read_bytes())
    for name in ('runtime_policy.h','telemetry.h'):(bundle/name).write_bytes((ROOT/'embedded/arm_live_panel_p56'/name).read_bytes())
    r=dict(status='building',stages=[],frozen='results/p52-export-20261024T043113Z/report.json',
        frozen_sha256=sha(ROOT/'results/p52-export-20261024T043113Z/report.json'),board_operations=False,
        scope='closed three-class controlled operation; rejection checks are not universal unknown recognition')
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
                    rows=[json.loads(v) for v in (folder/'ai-history.jsonl').read_text().splitlines()]
                    ok=ok and s['display_revision']=='p56' and s['retained_prefix_bytes']==262144 and len(rows)>=3 and rows[-1]['state']=='STOPPED' and all(v['accepted_class']==-1 for v in rows) and rows[0]['state']=='CALIBRATION_REQUIRED'
            r['stages'].append(dict(label='mock-'+(fault or 'good'),exit_code=q.returncode,gate_passed=bool(ok)));write(out/'report.json',r)
            if not ok:raise ValueError('lifecycle failed: '+fault)
        r.update(status='passed_build_and_12_lifecycle_cases_policy_tests_pending',binary=rel(arm),binary_sha256=sha(arm),host=rel(host),
            inputs_sha256={rel(p):sha(p) for p in [Path(__file__),ROOT/'embedded/arm_live_panel_p48/arm_live_panel_p48.c',ROOT/'embedded/arm_panel_p48/arm_panel.c',ROOT/'embedded/arm_rx_full_p36/arm_rx_full_p36.c',*bundle.iterdir()]})
    except Exception as e:r.update(status='failed_not_deployed',error=repr(e))
    write(out/'report.json',r);print(out);print(r['status']);return int(not r['status'].startswith('passed'))
if __name__=='__main__':raise SystemExit(main())
