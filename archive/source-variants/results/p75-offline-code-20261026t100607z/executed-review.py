"""Native P69 full-policy/render/shot replay using archived real P68 blocks."""
import argparse,json,subprocess,xml.etree.ElementTree as ET
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
from PIL import Image
from p45_checkpoint import ROOT,read,write,sha,rel
from p36_build_rx_full import posix
from p68_review_rf import occupied_bandwidth,welch_power_spectrum
from p37_review_archives import decode_rx12

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--build',required=True,type=Path);a=ap.parse_args();b=read(a.build)
    if b['status']!='passed_P75_phase_candidate_build_lifecycle12_not_deployed':raise ValueError('build required')
    for p,h in b['inputs_sha256'].items():
        if sha(ROOT/p)!=h:raise ValueError('changed input '+p)
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p75-offline-%Y%m%dT%H%M%SZ');out.mkdir()
    r=dict(status='reviewing',build=rel(a.build),build_sha256=sha(a.build),board_operations=False,
        scope='previously exposed RF blocks plus synthetic clipping and stale controls; not new AI accuracy')
    try:
        xml=ROOT/'results/p69-math-tests-20261026.xml';suite=ET.parse(xml).getroot().find('testsuite')
        if suite is None or suite.get('tests')!='15' or suite.get('errors')!='0' or suite.get('failures')!='0':raise ValueError('15 numeric/gate tests required')
        (out/'math-tests.xml').write_bytes(xml.read_bytes())
        bundle=(ROOT/b['binary']).parent/'bundle'
        monitor=(bundle/'monitor.c').read_text().replace('int main(int argc, char **argv) {','int candidate_main(int argc, char **argv) {')
        (out/'test_monitor.c').write_text(monitor,encoding='utf-8')
        harness='''#include "test_monitor.c"
int main(int argc,char **argv) {
    if(argc!=3||setenv("P56_CONTROL_FILE",argv[2],1)||p56_initialize())return 2;
    panel_sample_rate_hz=30720000;p69_lo=2450000000;
    char request[1024];snprintf(request,sizeof request,"%s/shot",argv[1]);
    if(setenv("P56_SHOT_FILE",request,1))return 2;
    FILE *script=fopen("STEPS","r");if(!script)return 2;
    fb=calloc(PANEL_W*PANEL_H,4);fb_stride_words=PANEL_W;if(!fb)return 2;
    unsigned char input[262144];int16_t iq[131072];float window[FFT_N];double acc[FFT_N];
    for(int n=0;n<FFT_N;n++)window[n]=.5f-.5f*(float)cos(2*M_PI*n/FFT_N);
    char op[8],path[1024];unsigned index=0;
    while(fscanf(script,"%7s %1023s",op,path)==2) {
        if(!strcmp(op,"absent"))unlink(argv[2]);
        else if(strcmp(op,"keep")) {
            FILE *f=fopen(argv[2],"wb");if(!f)return 2;
            const char *boot=!strcmp(op,"stale")?"00000000-0000-0000-0000-000000000000":p56_boot;
            fprintf(f,"P56CAL1 %s %s %s\\n",boot,AI_MODEL_SHA,"11111111111111111111111111111111");fclose(f);
        }
        FILE *f=fopen(path,"rb");if(!f)return 2;
        if(fread(input,1,sizeof input,f)!=sizeof input)return 2;
        fclose(f);if(p56_step(input))return 3;
        decode_latest(input,iq);struct metrics m={0};spectrum(iq,8192,2,8,0,window,acc,&m);
        p67_measure(iq,acc,index+1,index*.5);p69_measure(acc,window);
        if(p56_evidence(argv[1],index+1)||p69_evidence(argv[1],"running",0))return 3;
        p69_draw(acc,&m,2,8192,index,0,8);p56_line();
        f=fopen(request,"w");if(!f)return 3;fprintf(f,"%u\\n",index+1);fclose(f);
        if(p56_shot(argv[1],input,1)||p69_shot(argv[1]))return 3;
        index++;
    }
    fclose(script);p56_state=P56_STOPPED;p56_class=-1;
    if(p69_evidence(argv[1],"finished",1))return 3;
    if(p56_history)fclose(p56_history);
    free(fb);return 0;
}'''
        files=ROOT/'results/p59-p68-rf-dashboard-20261026T022621942828Z/files'
        clip=out/'clipped.bin';clip.write_bytes(np.full(65536*2,2047,dtype='<i2').tobytes())
        steps=[('absent',files/'shot-01.bin'),('valid',files/'shot-01.bin')]+[('keep',files/'shot-01.bin')]*3
        steps += [('keep',files/'shot-02.bin')]*2+[('keep',files/f'shot-{i:02d}.bin') for i in (3,4,5,6)]
        steps += [('keep',clip),('stale',files/'shot-03.bin')]
        manifest=out/'steps.txt';manifest.write_text(''.join(op+' '+posix(p)+'\n' for op,p in steps),encoding='ascii')
        (out/'harness.c').write_text(harness.replace('STEPS',posix(manifest)),encoding='ascii')
        flags=['-std=c11','-O2','-Wall','-Wextra','-Werror','-fno-fast-math','-ffp-contract=off','-pthread']
        q=subprocess.run(['wsl.exe','--exec','gcc',*flags,'-I',posix(out),'-I',posix(bundle),'-I',posix(ROOT/'embedded/vendor/libiio-v0.24'),posix(out/'harness.c'),'-o',posix(out/'harness'),'-ldl','-lm','-lrt'],capture_output=True,timeout=120)
        (out/'build.stderr').write_bytes(q.stderr)
        if q.returncode:raise ValueError('native replay compile failed')
        data=out/'data';data.mkdir()
        q=subprocess.run(['wsl.exe','--exec',posix(out/'harness'),posix(data),posix(out/'control')],capture_output=True,timeout=60)
        (out/'replay.stdout').write_bytes(q.stdout);(out/'replay.stderr').write_bytes(q.stderr)
        if q.returncode:raise ValueError('native replay failed '+str(q.returncode))
        rows=[json.loads(line) for line in (data/'metrics-history.jsonl').read_text().splitlines()]
        expected=['CALIBRATION_REQUIRED']*6+['VALID']*4+['NO_USABLE_SIGNAL','CLIPPED','CALIBRATION_REQUIRED','STOPPED']
        r['states']=[row['measurement_status'] for row in rows]
        if r['states']!=expected:raise ValueError('measurement validity/reset/stop mismatch')
        for index,row in enumerate(rows[:-1],1):
            metrics=read(data/f'shot-{index:02d}.metrics.json');ai=read(data/f'shot-{index:02d}.json')
            if metrics!=row or metrics['source_block_sequence']!=ai['source_block_sequence']:raise ValueError('shot AI/metrics race or stale block')
            pair=decode_rx12((data/f'shot-{index:02d}.bin').read_bytes());x=pair[:,0].astype(float)+1j*pair[:,1]
            if row['valid']:
                spec=welch_power_spectrum(x[:8192],30720000,1024,overlap=0)
                center=ai['common_IF_hz'];gold=occupied_bandwidth(spec.frequency_hz,spec.psd,(center-600000,center+600000),rf_lo_hz=2450000000)
                if abs(gold.bandwidth_hz-row['ROI_99_width_hz'])>5 or abs(gold.center_baseband_hz-row['center_offset_hz'])>5:raise ValueError('native/Python ROI numerics differ')
            elif any(row[key] is not None for key in ('ROI_99_width_hz','center_offset_hz','LO_plus_center_hz','ROI_power_counts_squared')):raise ValueError('stale invalid numeric value')
        if rows[-1]['valid'] or rows[-1]['LO_plus_center_hz'] is not None:raise ValueError('stale final measurement')
        for index,label in ((8,'BPSK'),(9,'QPSK'),(10,'16QAM'),(11,'no-signal'),(12,'clipped'),(13,'stale-calibration')):
            Image.frombytes('RGB',(800,480),(data/f'shot-{index:02d}.raw').read_bytes(),'raw','BGRX').save(out/(label+'-replay.png'))
        # The original nineteen-step policy harness must also stay bit-identical.
        source=ROOT/'results/p56-policy-20261024T085402Z'
        q=subprocess.run(['wsl.exe','--exec','gcc',*flags,'-I',posix(out),'-I',posix(bundle),'-I',posix(ROOT/'embedded/vendor/libiio-v0.24'),posix(ROOT/'tests/native/p56_policy_harness.c'),'-o',posix(out/'policy-host'),'-ldl','-lm','-lrt'],capture_output=True,timeout=120)
        (out/'policy-build.stderr').write_bytes(q.stderr)
        if q.returncode:raise ValueError('policy compile failed')
        q=subprocess.run(['wsl.exe','--exec',posix(out/'policy-host'),posix(source/'steps.txt'),posix(out/'policy-control')],capture_output=True,timeout=60)
        (out/'policy.stdout').write_bytes(q.stdout)
        policy=[json.loads(line) for line in q.stdout.decode().splitlines() if line.startswith('{')]
        original=read(source/'report.json')['rows']
        # Logits intentionally change under the new inference; all other policy
        # fields must still be identical on these fixed safety fixtures.
        strip=lambda row:{k:v for k,v in row.items() if k!='logits'}
        if q.returncode or [strip(x) for x in policy]!=[strip(x) for x in original]:raise ValueError('policy invariants changed')
        from p74_phase_pool import phase_pool_logits
        from rfsig.rf_ai_calibration import adapt_calibrated
        frozen=read(ROOT/b['frozen'])
        with np.load(ROOT/frozen['frozen_inputs']['quantized']['path'],allow_pickle=False) as z:quant=dict(z)
        policy_paths=[line.split(' ',1)[1] for line in (source/'steps.txt').read_text().splitlines()]
        checked=0
        for item,remote in zip(policy,policy_paths):
            if min(item['predictions'])<0:continue
            # This is an original P56 fixture, decoded from its packed I/Q.
            local=Path(remote.replace('/mnt/c/','C:/',1))
            pair=decode_rx12(local.read_bytes());iq=pair[:,0].astype(float)+1j*pair[:,1]
            cal=dict(status='known_tone_common_IF_calibrated',frequency_hz=item['common_IF_hz'],shared_across_modulation_classes=True,modulation_labels_used=False)
            frames,_=adapt_calibrated(iq,sample_rate_hz=30720000,calibration=cal)
            expected_logits=phase_pool_logits(np.asarray(frames,dtype=np.complex64),quant)
            np.testing.assert_allclose(item['logits'],expected_logits,rtol=1e-4,atol=5e-4)
            np.testing.assert_array_equal(item['predictions'],expected_logits.argmax(axis=1))
            checked+=1
        r.update(policy_invariants_match=True,policy_rows=policy,new_logits_independent_Python_cases=checked)

        r.update(status='passed_P75_integrated14_states_shots_policy19',rows=rows,policy_steps=19,
            replay_harness=rel(out/'harness'),replay_harness_sha256=sha(out/'harness'))
    except Exception as e:r.update(status='failed_P75_offline_not_deployed',error=repr(e))
    r['files_sha256']={rel(p):sha(p) for p in out.rglob('*') if p.is_file() and p.name!='report.json'}
    write(out/'report.json',r);print(out);print(r['status']);return int(not r['status'].startswith('passed'))
if __name__=='__main__':raise SystemExit(main())
