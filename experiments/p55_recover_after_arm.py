"""Serialize actual ARM acceptance, guarded cached-profile reboot and review."""
import json,subprocess,sys,time
from datetime import datetime,timezone
from pathlib import Path
from p45_checkpoint import ROOT,read,write,sha,rel

def main():
    arm_path=ROOT/'results/p52-ARM-20261024T075009Z/report.json'
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p55-recovery-flow-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    r=dict(status='waiting_for_ARM_owner_release',stages=[],ARM=rel(arm_path),TX_operations=False)
    def save():write(out/'report.json',r)
    def run(label,script,wanted,*params,timeout=240):
        print(label,flush=True);r['status']=label;save()
        with (out/(label+'.stdout')).open('wb') as a,(out/(label+'.stderr')).open('wb') as b:
            q=subprocess.run([sys.executable,str(ROOT/'experiments'/script),*map(str,params)],cwd=ROOT,stdout=a,stderr=b,timeout=timeout)
        paths=[Path(s.strip())/'report.json' for s in (out/(label+'.stdout')).read_text('utf-8').splitlines() if Path(s.strip()).is_absolute() and (Path(s.strip())/'report.json').is_file()]
        row=dict(label=label,exit_code=q.returncode);r['stages'].append(row);save()
        if q.returncode or len(paths)!=1:raise ValueError(label+' failed')
        row.update(report=rel(paths[0]),report_sha256=sha(paths[0]));r[label]=rel(paths[0]);save()
        if read(paths[0])['status']!=wanted:raise ValueError(label+' status failed')
        return paths[0]
    save();(out/'executed.py').write_bytes(Path(__file__).read_bytes())
    try:
        deadline=time.monotonic()+1200
        while True:
            try:arm=read(arm_path)
            except json.JSONDecodeError:time.sleep(.2);continue
            if arm['serial_closed']:
                if arm['status']!='passed_independent_real_RF_ARM_full_frontend_CNN_matches_Python':raise ValueError('ARM acceptance failed')
                break
            if time.monotonic()>deadline:raise ValueError('ARM still owns serial')
            time.sleep(3)
        r['ARM_sha256']=sha(arm_path);save()
        cycle=run('warm_cycle','p55_recovery_cycle.py','passed_long_running_RX_LCD_progress_and_independent_idle',
            '--candidate-suite','results/p48-suite-20261022T133549Z/report.json','--build-report','results/p48-build-20261022T132941Z/report.json',
            '--current-status-report','results/p43-status-20261023T130435Z/report.json','--preparation-report','results/p43-preparation-20261022T030536Z/report.json',
            '--reuse-cycle','results/p43-boot-cycle-20261023T130008Z/report.json','--reuse-review','results/p42-review-20261023T130237Z/report.json',
            '--factory-preflight','results/p46-preflight-20261024T074202Z/report.json','--rx-restore','results/p55-rx-profile-20261024T074852Z/report.json')
        review=run('review','p42_review_session.py','passed_P42_archives_and_independent_NumPy',
            '--trial',cycle,'--merged-trial',cycle.parent/'hardware-trial.json','--with-screen')
        run('units','p48_verify_units.py','passed_P48_frequency_units_and_exact_framebuffer_glyphs','--trial',cycle,'--review',review)
        r.update(status='passed_ARM_then_current_warm_RF_LCD_clock_IQ_pixels_and_units',expected_boot=read(cycle)['expected_boot'])
    except Exception as e:r.update(status='failed_recovery_stop_no_reboot_retry',error=repr(e))
    save();print(out);print(r['status']);return 0 if r['status'].startswith('passed_') else 1
if __name__=='__main__':raise SystemExit(main())
