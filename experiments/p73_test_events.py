"""Exercise actual C event hook: boundedness, same-update files, error rejection."""
import argparse,json,subprocess
from datetime import datetime,timezone
from pathlib import Path
from p45_checkpoint import ROOT,read,write,sha,rel
from p36_build_rx_full import posix


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--build',required=True,type=Path);a=ap.parse_args();b=read(a.build)
    if b['status']!='built_P73_event_diagnostic_offline_tests_pending':raise ValueError('candidate build required')
    for p,h in b['inputs_sha256'].items():
        if sha(ROOT/p)!=h:raise ValueError('candidate input changed')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p73-offline-%Y%m%dT%H%M%SZ');out.mkdir()
    bundle=(ROOT/b['binary']).parent/'bundle'
    (out/'test_monitor.c').write_text((bundle/'monitor.c').read_text().replace('int main(int argc, char **argv) {','int candidate_main(int argc, char **argv) {'),encoding='utf-8')
    harness=r'''#include "test_monitor.c"
int main(int argc,char **argv) {
    if(argc!=4||p56_initialize())return 2;
    FILE *steps=fopen(argv[2],"r");if(!steps)return 2;
    p56_begin=now_s();panel_sample_rate_hz=30720000;p69_lo=2450000000;
    unsigned seq,state,ready,enabled,value,damage;double elapsed;
    unsigned char input[262144];
    while(fscanf(steps,"%lf %u %u %u %u %u %u",&elapsed,&seq,&state,&ready,&enabled,&value,&damage)==7) {
        if(setenv("P73_EVENT_CAPTURE",enabled?"1":"0",1))return 2;
        p56_ready=(int)ready;p56_state=(enum p56_state)state;p56_class=state==P56_CLASSIFIED?2:-1;
        p67_sequence=seq;p67_elapsed=elapsed;memset(input,(int)value,sizeof input);
        if(p56_evidence(argv[1],seq)||p69_evidence(argv[1],"running",0))return 3;
        if(damage) {
            char path[1024];snprintf(path,sizeof path,"%s/metrics.json",argv[1]);
            FILE *f=fopen(path,"wb");if(!f)return 3;fputs("{\"source_block_sequence\":999999}\n",f);fclose(f);
        }
        int result=p73_event(argv[1],input);
        printf("{\"sequence\":%u,\"result\":%d,\"total\":%u}\n",seq,result,p73_capture.total);
    }
    fclose(steps);if(p56_history)fclose(p56_history);if(p69_history)fclose(p69_history);
    return 0;
}'''
    (out/'harness.c').write_text(harness,encoding='ascii')
    # state 3=no-signal, 5=uncertain, 6=classified. Separate process for stale
    # evidence so a deliberately rejected attempt cannot obscure quota checks.
    steps=[(0,1,6,1,0,1,0),(1,2,3,1,1,2,0),(2,3,6,0,1,3,0),
           (10,4,6,1,1,4,0),(11,5,6,1,1,5,0),(12,6,6,1,1,6,0),
           (12.5,7,6,1,1,7,0),(14,8,6,1,1,8,0),(16,9,6,1,1,9,0),
           (18,10,6,1,1,10,0),(18.5,11,5,1,1,11,0),(19,12,5,1,1,12,0),
           (20.5,13,5,1,1,13,0),(22.5,14,5,1,1,14,0),(24.5,15,5,1,1,15,0),
           (119,16,6,1,1,16,0),(120,17,6,1,1,17,0),(122,18,6,1,1,18,0),
           (124,19,6,1,1,19,0),(126,20,6,1,1,20,0),(126,21,5,1,1,21,0),
           (128,22,5,1,1,22,0),(130,23,5,1,1,23,0),(132,24,5,1,1,24,0),
           (134,23,5,1,1,25,0)]
    expected_ids=[6,8,9,11,13,14,17,18,19,21,22,23]
    manifest=out/'steps.txt';manifest.write_text(''.join(' '.join(map(str,row))+'\n' for row in steps),encoding='ascii')
    r=dict(status='testing',build=rel(a.build),build_sha256=sha(a.build),board_operations=False,gates=[])
    def check(name,ok):
        r['gates'].append(dict(name=name,passed=bool(ok)))
        if not ok:raise ValueError(name)
    def run(label,cmd,timeout=120):
        q=subprocess.run([str(x) for x in cmd],capture_output=True,timeout=timeout)
        (out/(label+'.stdout')).write_bytes(q.stdout);(out/(label+'.stderr')).write_bytes(q.stderr)
        check(label+' exit',q.returncode==0);return q
    try:
        flags=['-std=c11','-O2','-Wall','-Wextra','-Werror','-fno-fast-math','-ffp-contract=off','-pthread']
        run('harness-build',['wsl.exe','--exec','gcc',*flags,'-I',posix(bundle),'-I',posix(ROOT/'embedded/vendor/libiio-v0.24'),posix(out/'harness.c'),'-o',posix(out/'harness'),'-ldl','-lrt','-lm'])
        data=out/'data';data.mkdir()
        q=run('hook',['wsl.exe','--exec',posix(out/'harness'),posix(data),posix(manifest),'unused'])
        result=[json.loads(l) for l in q.stdout.decode().splitlines()]
        events=[json.loads(l) for l in (data/'event-history.jsonl').read_text().splitlines()]
        check('all states exercised',len(result)==len(steps) and all(v['result']==0 for v in result))
        check('disabled, ready and two-second onset gate',all(v['total']==0 for v in result[:5]))
        check('twelve cap with per-state/age quotas',len(events)==12 and [v['source_block_sequence'] for v in events]==expected_ids)
        for e in events:
            base=f'event-{e["id"]:02d}';seq=e['source_block_sequence']
            ai=read(data/(base+'.json'));m=read(data/(base+'.metrics.json'))
            check('same-update metadata '+base,ai['source_block_sequence']==m['source_block_sequence']==seq and ai['state']==m['AI_state']==e['state'])
            check('exact IQ bytes '+base,(data/(base+'.bin')).read_bytes()==bytes([seq])*262144)
        check('last duplicate did not overwrite event 12',(data/'event-12.bin').read_bytes()==bytes([23])*262144)
        check('bounded IQ bytes',sum(p.stat().st_size for p in data.glob('event-*.bin'))==12*262144)
        for name,rows in [('stale',[(10,1,6,1,1,1,0),(12,2,5,1,1,2,1)]),
                          ('duplicate',[(10,1,6,1,1,1,0),(12,2,6,1,1,2,0),(15,2,5,1,1,3,0)]),
                          ('gap',[(10,1,6,1,1,1,0),(12,2,6,1,1,2,0),(14,3,3,1,1,3,0),(15,4,5,1,1,4,0),(16,5,5,1,1,5,0),(17,6,5,1,1,6,0)])]:
            folder=out/name;folder.mkdir();script=out/(name+'.txt');script.write_text(''.join(' '.join(map(str,row))+'\n' for row in rows),encoding='ascii')
            q=run(name,['wsl.exe','--exec',posix(out/'harness'),posix(folder),posix(script),'unused'])
            result=[json.loads(l) for l in q.stdout.decode().splitlines()]
            if name=='stale':check('mismatched metrics rejected before any IQ file',result[-1]['result']==1 and not list(folder.glob('event-*')))
            elif name=='duplicate':check('duplicate sequence never rewrites',result[-1]['total']==1 and (folder/'event-01.bin').read_bytes()==bytes([2])*262144)
            else:check('no-signal resets onset guard',[v['total'] for v in result]==[0,1,1,1,1,2])
        # Run the full unchanged 19-case frozen policy against this candidate.
        run('policy-build',['wsl.exe','--exec','gcc',*flags,'-I',posix(out),'-I',posix(bundle),'-I',posix(ROOT/'embedded/vendor/libiio-v0.24'),posix(ROOT/'tests/native/p56_policy_harness.c'),'-o',posix(out/'policy-host'),'-ldl','-lm','-lrt'])
        old=ROOT/'results/p56-policy-20261024T085402Z'
        q=run('policy',['wsl.exe','--exec',posix(out/'policy-host'),posix(old/'steps.txt'),posix(out/'policy-control')])
        check('frozen policy 19-case exact parity',[json.loads(l) for l in q.stdout.decode().splitlines() if l.startswith('{')]==read(old/'report.json')['rows'])
        r.update(status='passed_P73_bounded_same_update_capture_and_frozen_policy',events=events,complete_iq_triplets=12,frozen_policy_cases=19)
    except Exception as e:r.update(status='failed_P73_offline',error=repr(e))
    write(out/'report.json',r);print(out);print(r['status']);return int(r['status'].startswith('failed'))


if __name__=='__main__':raise SystemExit(main())
