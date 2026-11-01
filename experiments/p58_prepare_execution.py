"""Predeclare cold ten-minute observation and 3x45 s bounded source protocol."""
import argparse
from datetime import datetime,timezone
from pathlib import Path
from p45_checkpoint import ROOT,read,write,sha,rel
from p53_build_live_ai import replace_once as sub
from p58_boot_contract import validate_boot

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--attachment',required=True,type=Path);args=ap.parse_args();a=read(args.attachment)
    bootpath=ROOT/a['inputs']['boot']['path'];boot=validate_boot(bootpath)
    if not boot.get('true_power_cycle_verified'):raise ValueError('actual cold proof required')
    for item in a['inputs'].values():
        if sha(ROOT/item['path'])!=item['sha256']:raise ValueError('attachment input changed')
    controller=ROOT/a['controller'];reviewer=ROOT/a['reviewer']
    if sha(controller)!=a['controller_sha256'] or sha(reviewer)!=a['reviewer_sha256']:raise ValueError('attachment bytes changed')
    text=controller.read_text(encoding='utf-8');review=reviewer.read_text(encoding='utf-8')
    text=sub(text,'duration=900000;seconds=12;cycles=1','duration=900000;seconds=45;cycles=1')
    text=sub(text,"('p57-live-'+stamp)","('p58-live-'+stamp)")
    text=sub(text,"        held=time.monotonic()\n        while time.monotonic()-held<6:\n            sample();time.sleep(.5)",
        "        held=time.monotonic()\n        while True:\n            a=sample()\n            if a['state']=='STOPPED':raise ValueError('RX stopped before cold observation target')\n            if a['elapsed_s']>=630 and time.monotonic()-held>=6:break\n            if time.monotonic()-held>700:raise ValueError('cold observation outer deadline')\n            time.sleep(4)")
    text=sub(text,"    def save():write(out/'report.json',r)","    r.update(user_power_cycle_verified=True,cold_observation_target_s=630,TX_seconds_per_class=45)\n    def save():write(out/'report.json',r)")
    review=sub(review,"strftime('p57-review-%Y%m%dT%H%M%SZ')","strftime('p58-review-%Y%m%dT%H%M%SZ')")
    review=sub(review,"check('no unexplained multi-second UI stall',", "check('cold ten-minute observation reached',t.get('user_power_cycle_verified') and t['native_summary']['elapsed_software_s']>=630)\n        check('no unexplained multi-second UI stall',")
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p58-execution-%Y%m%dT%H%M%SZ');out.mkdir()
    for name,data in (('controller.py',text),('review.py',review)):
        compile(data,str(out/name),'exec');(out/name).write_text(data,encoding='utf-8')
    r=dict(status='prepared_cold_630s_observation_3x45s_source_and_unchanged_thresholds',board_operations=False,
        attachment=rel(args.attachment),attachment_sha256=sha(args.attachment),boot=rel(bootpath),boot_sha256=sha(bootpath),
        controller=rel(out/'controller.py'),controller_sha256=sha(out/'controller.py'),reviewer=rel(out/'review.py'),reviewer_sha256=sha(out/'review.py'),
        source_seconds_each=45,pilot_seconds=15,minimum_native_elapsed_s=630,minimum_final_source_off_s=6,
        coverage_threshold=.70,conditional_accuracy_threshold=.90,model_changed=False,native_changed=False,automatic_TX_at_boot=False)
    write(out/'report.json',r);print(out);print(r['status'])
if __name__=='__main__':main()
