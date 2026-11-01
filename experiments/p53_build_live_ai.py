"""Build an isolated bounded RX/LCD/AI candidate from the accepted P48 lifecycle.

The P48 persistent binary/source remains unchanged. Classification uses the
frozen P52 frontend/weights on one complete DMA block, with explicit common IF.
"""
import argparse,json,subprocess
from datetime import datetime,timezone
from pathlib import Path
from p45_checkpoint import ROOT,read,write,sha,rel
from p36_build_rx_full import TOOL,posix


def replace_once(text,old,new):
    if text.count(old)!=1:raise ValueError('candidate parent anchor differs: '+old[:50])
    return text.replace(old,new,1)


def generate(parent,frontend,frequency,mode):
    # Nothing here uses a true modulation label. Mode is validation-selected.
    core=frontend.split('int main(int argc,char **argv) {')[0]
    if core==frontend or core.count('if(emit) printf(')!=1:raise ValueError('frozen RF frontend differs')
    core=core.replace('static int infer_block(', 'static int ai_predictions[3];\nstatic double ai_logits[3][3];\nstatic int infer_block(',1)
    core=core.replace('        if(emit) printf(', '        ai_predictions[frame]=predicted;memcpy(ai_logits[frame],logits,sizeof logits);\n        if(emit) printf(',1)
    text=parent
    for file in ('../arm_rx_full_p36/arm_rx_full_p36.c','../arm_panel_p48/arm_panel.c'):
        absolute=posix((ROOT/'embedded/arm_live_panel_p48'/file).resolve())
        text=replace_once(text,'"'+file+'"','"'+absolute+'"')
    text=replace_once(text,'#define PREFIX_FRAMES 8192u','#include "ai_impl.h"\n#define PREFIX_FRAMES 65536u')
    text=replace_once(text,'int main(int argc, char **argv) {','''static double ai_ms;
static int save_ai(const char *directory,uint64_t sequence) {
    char temporary[1024],final[1024];
    if(snprintf(temporary,sizeof temporary,"%s/ai.next",directory)>=(int)sizeof temporary
       ||snprintf(final,sizeof final,"%s/ai.json",directory)>=(int)sizeof final)return 1;
    FILE *f=new_file(directory,"ai.next");if(!f)return 1;
    fprintf(f,"{\\"schema\\":\\"rfsig.live_ai.v1\\",\\"source_block_sequence\\":%" PRIu64
        ",\\"common_IF_hz\\":%.17g,\\"mode\\":\\"%s\\",\\"model_sha256\\":\\"%s\\",\\"frames\\":3,"
        "\\"predictions\\":[%d,%d,%d],\\"logits\\":[[%.17g,%.17g,%.17g],[%.17g,%.17g,%.17g],[%.17g,%.17g,%.17g]],"
        "\\"full_frontend_CNN_ms\\":%.9g,\\"class_order\\":[\\"BPSK\\",\\"QPSK\\",\\"16QAM\\"],"
        "\\"controlled_conditions_only\\":true,\\"confidence_calibrated\\":false,\\"ADC_gaps\\":\\"unknown\\"}\\n",
        sequence,AI_IF_HZ,AI_MODE,AI_MODEL_SHA,ai_predictions[0],ai_predictions[1],ai_predictions[2],
        ai_logits[0][0],ai_logits[0][1],ai_logits[0][2],ai_logits[1][0],ai_logits[1][1],ai_logits[1][2],
        ai_logits[2][0],ai_logits[2][1],ai_logits[2][2],ai_ms);
    int bad=ferror(f);if(fclose(f))bad=1;
    if(bad||rename(temporary,final)){unlink(temporary);return 1;}return 0;
}
static void ai_line(void) {
    const char *names[]={"BPSK","QPSK","16QAM"};char line[128];
    snprintf(line,sizeof line,"AI: %s / %s / %s | %.1f ms | controlled 3 classes",
        names[ai_predictions[0]],names[ai_predictions[1]],names[ai_predictions[2]],ai_ms);
    latest_line(PANEL_H-24,line);
}
int main(int argc, char **argv) {''')
    text=replace_once(text,'number(argv[arg+1], 0, 86400000, &duration_ms)','number(argv[arg+1], 100, 10000, &duration_ms)')
    text=text.replace('arm-live-panel-p42 [--analyse-only] NEW_DIRECTORY DURATION_MS_0_UNTIL_SIGNAL_OR_UP_TO_86400000 UI_INTERVAL_MS_100_1000',
        'arm-live-ai-p53 [--analyse-only] NEW_DIRECTORY DURATION_MS_100_10000 UI_INTERVAL_MS_100_1000')
    text=replace_once(text,'    int arg = 1, analyse_only = 0, duration_ms, interval_ms;',
        '    if(fesetround(FE_TONEAREST))return 2;\n    int arg = 1, analyse_only = 0, duration_ms, interval_ms;')
    text=replace_once(text,'            double t1 = now_s();','''            double ai_begin=now_s();memcpy(packed,shown,sizeof packed);
            if(infer_block(AI_IF_HZ,!strcmp(AI_MODE,"int8"),0)){reason="AI_input_invalid";progress_error=1;break;}
            ai_ms=1000*(now_s()-ai_begin);
            if(save_ai(argv[arg],sequence)){reason="AI_evidence_write_failed";progress_error=1;break;}
            double t1 = now_s();''')
    text=replace_once(text,'                latest_line(PANEL_H-24, "LATEST PREFIXES | ADC gaps unknown | digital bin power | no AI");','                ai_line();')
    old='        latest_line(PANEL_H-24, status == 0 ? "RX STOPPED | last displayed prefix | ADC gaps unknown | no AI" : clean_stop ? "RX STOPPED BY REQUEST | last displayed prefix | no AI" : "RX FAILED | last displayed prefix | no AI");'
    text=replace_once(text,old,'        ai_line();')
    text=replace_once(text,'    if (map) munmap(map, map_length);','''    if(map && updates) {
        FILE *capture=new_file(argv[arg],"fb.raw");int bad=capture==NULL;
        if(capture) {
            for(int y=0;y<PANEL_H;y++)if(fwrite(fb+(size_t)y*fb_stride_words,4,PANEL_W,capture)!=PANEL_W)bad=1;
            if(fclose(capture))bad=1;
        }
        if(bad){status=1;reason="AI_framebuffer_save_failed";}
    }
    if (map) munmap(map, map_length);''')
    # Spectrum averages the first 8192 samples; AI uses all 65536 of same block.
    text=text.replace('spectrum(iq, PREFIX_FRAMES, 2, 8, 0, window, acc, &m);','spectrum(iq, 8192, 2, 8, 0, window, acc, &m);')
    text=text.replace('draw(acc, &m, 2, PREFIX_FRAMES,','draw(acc, &m, 2, 8192,')
    text=text.replace('(t1-t0)*1000','(ai_begin-t0)*1000')
    text=text.replace('\\"display_revision\\":\\"p48\\"','\\"display_revision\\":\\"p53\\"')
    return text,core


def main():
    p=argparse.ArgumentParser();p.add_argument('--ARM-review',required=True,type=Path)
    p.add_argument('--source-report',type=Path);p.add_argument('--calibration',type=Path);args=p.parse_args()
    reviewed=read(args.ARM_review)
    if reviewed['status']!='passed_independent_real_RF_ARM_full_frontend_CNN_matches_Python':raise ValueError('actual ARM inference acceptance required')
    frozen_path=ROOT/reviewed['frozen'];frozen=read(frozen_path)
    if sha(frozen_path)!=reviewed['frozen_sha256']:raise ValueError('frozen model changed')
    for v in frozen['frozen_inputs'].values():
        if sha(ROOT/v['path'])!=v['sha256']:raise ValueError('frozen inputs changed')
    if sha(ROOT/reviewed['evaluation'])!=reviewed['evaluation_sha256']:raise ValueError('ARM parent evaluation changed')
    ev=read(ROOT/reviewed['evaluation']);batch=read(ROOT/ev['test_batch'])
    if sha(ROOT/ev['test_batch'])!=ev['test_batch_sha256']:raise ValueError('evaluated test batch changed')
    # One independent single-tone-derived common IF from final session, shared
    # by every modulation, is fixed before this separate display demonstration.
    frequency=next(v['common_IF_hz'] for v in reversed(ev['fixtures']))
    source_report=batch['groups'][-1]['source_report'];source_sha=batch['groups'][-1]['source_sha256'];calibration_provenance=None
    if args.source_report or args.calibration:
        if not args.source_report or not args.calibration:raise ValueError('both current source and tone-only calibration required')
        current_source=read(args.source_report);current_calibration=read(args.calibration)
        if (current_source['status']!='guard_and_peak256_sources_restored_inspected_checked_no_TX'
            or current_calibration['status']!='passed_tone_only_common_IF_calibration'
            or current_calibration['expected_boot']!=current_source['RX_expected_boot']
            or current_calibration['source_report_sha256']!=sha(args.source_report)
            or current_calibration['modulation_labels_used'] or current_calibration['classifier_scores_used']):
            raise ValueError('current boot tone-only calibration differs')
        previous_source=read(ROOT/source_report)
        if current_source['source_report_sha256']!=previous_source['source_report_sha256']:raise ValueError('controlled waveform package changed')
        frequency=current_calibration['calibration']['frequency_hz'];source_report=rel(args.source_report);source_sha=sha(args.source_report)
        calibration_provenance=dict(path=rel(args.calibration),sha256=sha(args.calibration),expected_boot=current_source['RX_expected_boot'])
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p53-build-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    bundle=out/'bundle';bundle.mkdir()
    inputs={k:ROOT/frozen['frozen_inputs'][k]['path'] for k in ('frontend','C','header','taps')}
    parent=ROOT/'embedded/arm_live_panel_p48/arm_live_panel_p48.c'
    text,core=generate(parent.read_text(),inputs['frontend'].read_text(),frequency,frozen['selected_mode'])
    for key,name in (('C','trained_cnn_infer.c'),('header','trained_model.h'),('taps','rf_frontend.h')):
        (bundle/name).write_bytes(inputs[key].read_bytes())
    macros='#define AI_IF_HZ '+format(frequency,'.17g')+'\n#define AI_MODE "'+frozen['selected_mode']+'"\n#define AI_MODEL_SHA "'+frozen['frozen_inputs']['model']['sha256']+'"\n'
    (bundle/'ai_impl.h').write_text(macros+core,encoding='utf-8');(bundle/'monitor.c').write_text(text,encoding='utf-8')
    r=dict(status='building_isolated_live_AI_candidate',ARM_review=rel(args.ARM_review),ARM_review_sha256=sha(args.ARM_review),
        frozen=rel(frozen_path),frozen_sha256=sha(frozen_path),common_IF_hz=frequency,selected_mode=frozen['selected_mode'],
        source_report=source_report,source_sha256=source_sha,calibration_provenance=calibration_provenance,
        deployment_expected_boot=read(ROOT/source_report)['RX_expected_boot'],
        stages=[],board_operations=False,persistent_binary_changed=False,RF_configuration_writes=False,
        full_DMA_AI_frames=65536,spectrum_prefix_frames=8192,UI_interval_ms=500,maximum_duration_ms=10000,
        scope='controlled 3-class live demo; common tone calibration retained from current boot; no unknown rejection or calibrated confidence')
    def save():write(out/'report.json',r)
    def run(label,command):
        q=subprocess.run([str(a) for a in command],capture_output=True,timeout=120)
        (out/(label+'.stdout')).write_bytes(q.stdout);(out/(label+'.stderr')).write_bytes(q.stderr)
        r['stages'].append(dict(label=label,exit_code=q.returncode));save()
        if q.returncode:raise ValueError(label+' failed')
        return q.stdout.decode()
    save()
    try:
        flags=['-std=c11','-O2','-Wall','-Wextra','-Werror','-fno-fast-math','-ffp-contract=off','-pthread']
        host=out/'monitor-host';arm=out/'monitor-arm'
        run('host-build',['wsl.exe','--exec','gcc',*flags,'-I',posix(ROOT/'embedded/vendor/libiio-v0.24'),posix(bundle/'monitor.c'),'-o',posix(host),'-ldl','-lrt','-lm'])
        run('ARM-build',['wsl.exe','--exec',posix(TOOL/'arm-linux-gnueabihf-gcc'),*flags,'-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard','-marm','-I',posix(ROOT/'embedded/vendor/libiio-v0.24'),posix(bundle/'monitor.c'),'-o',posix(arm),'-ldl','-lrt','-lm'])
        elf=run('ARM-ELF',['wsl.exe','--exec',posix(TOOL/'arm-linux-gnueabihf-readelf'),'-h','-A','-l','-V',posix(arm)])
        if 'ELF32' not in elf or 'VFP registers' not in elf or '/lib/ld-linux-armhf.so.3' not in elf:raise ValueError('ARM ABI differs')
        run('mock-build',['wsl.exe','--exec','gcc','-std=c11','-O2','-Wall','-Wextra','-Werror','-shared','-fPIC','-I',posix(ROOT/'embedded/vendor/libiio-v0.24'),posix(ROOT/'tests/native/mock_latest_panel_p39.c'),'-o',posix(out/'libiio.so.0'),'-ldl','-lm','-pthread'])
        failures=[]
        for fault in ('','version','config','format','step','end','sample_size','create','short','after_config','cancel','join_hang'):
            folder=out/('mock-'+(fault or 'good'));log=out/('mock-'+(fault or 'good')+'.release')
            child=subprocess.run(['wsl.exe','--exec','env','LD_LIBRARY_PATH='+posix(out),'P36_MOCK_FAULT='+fault,'P36_MOCK_LOG='+posix(log),posix(host),'--analyse-only',posix(folder),'600','100'],capture_output=True,timeout=15)
            (out/('mock-'+(fault or 'good')+'.stdout')).write_bytes(child.stdout);(out/('mock-'+(fault or 'good')+'.stderr')).write_bytes(child.stderr)
            if fault=='join_hang':passed=child.returncode==3 and b'"cleanup_unconfirmed":true' in child.stdout and not log.exists() and not (folder/'summary.json').exists()
            else:
                summary=read(folder/'summary.json')
                passed=(child.returncode==0 if fault in ('','cancel') else child.returncode!=0) and summary['buffer_released'] and summary['context_released'] and not summary['cleanup_unconfirmed']
                if fault=='':
                    ai=read(folder/'ai.json');passed=passed and summary['display_updates']>=2 and summary['retained_prefix_bytes']==262144 and ai['source_block_sequence']==summary['last_display_sequence']
                    expected=run('mock-full-frontend',[ROOT/frozen['frozen_inputs']['host']['path'],folder/'last-display-packed.bin',str(frequency),frozen['selected_mode']])
                    import numpy as np
                    a=np.array([np.fromstring(s,sep=',') for s in expected.splitlines()]);np.testing.assert_allclose(ai['logits'],a[:,1:4],rtol=1e-4,atol=5e-4)
                    passed=passed and ai['predictions']==a[:,4].astype(int).tolist() and not ai['confidence_calibrated']
            r['stages'].append(dict(label='mock-'+(fault or 'good'),exit_code=child.returncode,gate_passed=bool(passed)));save()
            if not passed:failures.append(fault)
        if failures:raise ValueError('lifecycle/AI mock gates failed '+str(failures))
        all_inputs=[Path(__file__),parent,ROOT/'embedded/arm_panel_p48/arm_panel.c',ROOT/'embedded/arm_rx_full_p36/arm_rx_full_p36.c',ROOT/'embedded/arm_panel/font8x12.h',*bundle.iterdir()]
        if args.calibration:all_inputs.extend([args.calibration,args.source_report])
        r.update(status='passed_offline_live_AI_lifecycle_frontend_parity_ARM_build_not_deployed',binary=rel(arm),binary_sha256=sha(arm),
            inputs_sha256={rel(p):sha(p) for p in all_inputs},mock_cases=12,AI_on_board_not_yet_tested=True)
    except Exception as e:r.update(status='failed_candidate_not_deployed',error=repr(e))
    save();print(out);print(r['status'])
    return 0 if r['status'].startswith('passed_') else 1
if __name__=='__main__':raise SystemExit(main())
