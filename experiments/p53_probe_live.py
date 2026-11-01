"""Offline integration probe using OLD weights only; no AI acceptance claim."""
from datetime import datetime,timezone
import subprocess
from p45_checkpoint import ROOT,write,rel
from p36_build_rx_full import posix
from p53_build_live_ai import generate

def main():
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p53-probe-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    old=ROOT/'results/p52-frontend-probe-20261024T034039Z/bundle'
    for name in ('trained_model.h','rf_frontend.h','trained_cnn_infer.c'):(out/name).write_bytes((old/name).read_bytes())
    parent=ROOT/'embedded/arm_live_panel_p48/arm_live_panel_p48.c'
    text,core=generate(parent.read_text(),(ROOT/'embedded/tiny_cnn_probe/real_rf_infer.c').read_text(),993800,'int8')
    (out/'ai_impl.h').write_text('#define AI_IF_HZ 993800.0\n#define AI_MODE "int8"\n#define AI_MODEL_SHA "old_weights_probe_only"\n'+core)
    (out/'monitor.c').write_text(text)
    r=dict(status='building',old_weights_only=True,board_operations=False,AI_accepted=False,stages=[])
    def run(label,cmd):
        c=subprocess.run(cmd,capture_output=True,timeout=30)
        (out/(label+'.stdout')).write_bytes(c.stdout);(out/(label+'.stderr')).write_bytes(c.stderr)
        r['stages'].append(dict(label=label,exit_code=c.returncode));write(out/'report.json',r)
        if c.returncode:raise ValueError(label+' failed')
    try:
        run('compile',['wsl.exe','--exec','gcc','-std=c11','-O2','-Wall','-Wextra','-Werror','-fno-fast-math','-ffp-contract=off','-pthread','-I',posix(ROOT/'embedded/vendor/libiio-v0.24'),posix(out/'monitor.c'),'-o',posix(out/'monitor'),'-ldl','-lrt','-lm'])
        run('mock-build',['wsl.exe','--exec','gcc','-std=c11','-O2','-Wall','-Wextra','-Werror','-shared','-fPIC','-I',posix(ROOT/'embedded/vendor/libiio-v0.24'),posix(ROOT/'tests/native/mock_latest_panel_p39.c'),'-o',posix(out/'libiio.so.0'),'-ldl','-lm','-pthread'])
        run('mock-good',['wsl.exe','--exec','env','LD_LIBRARY_PATH='+posix(out),'P36_MOCK_LOG='+posix(out/'release.txt'),posix(out/'monitor'),'--analyse-only',posix(out/'data'),'600','100'])
        r['status']='passed_offline_candidate_old_weights_only_not_RF_AI_acceptance'
    except Exception as e:r.update(status='failed_offline_probe',error=repr(e))
    write(out/'report.json',r);print(out);print(r['status']);return 0 if r['status'].startswith('passed_') else 1
if __name__=='__main__':raise SystemExit(main())
