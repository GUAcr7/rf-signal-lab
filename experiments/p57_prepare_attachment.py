"""Derive a reviewed P56 controller for the already boot-owned P57 RX session.

The emitted full source is archived, not executed via an opaque eval. No new RX
process, upload, PL operation or reboot is added. Same frozen native binary.
"""
import argparse
from datetime import datetime,timezone
from pathlib import Path
from p45_checkpoint import ROOT,read,write,sha,rel
from p53_build_live_ai import replace_once as sub

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--boot',required=True,type=Path);ap.add_argument('--clock',required=True,type=Path);ap.add_argument('--source',required=True,type=Path);args=ap.parse_args()
    boot=read(args.boot);clock=read(args.clock);source=read(args.source)
    from p58_boot_contract import validate_boot
    validate_boot(args.boot)
    if (clock['status']!='read_only_evidence_collected' or clock['expected_boot']!=boot['expected_boot'] or clock.get('boot_id_after')!=boot['expected_boot']
        or not clock['register_read_gate']['allowed'] or clock.get('skip') or clock['tainted_after']!='0'
        or clock['registers']!={'status':1,'feedback':int('05f41002',16),'output0':25}):raise ValueError('gated current safe clock registers required')
    if source['status']!='passed_existing_guard_sources_rechecked_for_new_RX_boot_no_TX' or source['RX_expected_boot']!=boot['expected_boot'] or source['RX_boot_report_sha256']!=sha(args.boot):raise ValueError('source recheck required')
    for k,v in boot['installed_files_sha256'].items():
        if sha(args.boot.parent/'files'/k)!=v:raise ValueError('installed snapshot changed')
    parent=ROOT/'experiments/p56_runtime_trial.py';text=parent.read_text(encoding='utf-8')
    text=sub(text,'import argparse,json,re,time,uuid','import argparse,json,re,time,uuid\nimport sys\nsys.path.insert(0,'+repr(str(ROOT/'experiments'))+')')
    text=sub(text,"source_path=ROOT/'results/p52-restored-20261024T080358Z/report.json';sources=read(source_path)",
        'source_path=ROOT/'+repr(rel(args.source))+';sources=read(source_path)')
    text=sub(text,"stage='/tmp/p35-p56-'+stamp[9:15];directory=stage+'/data'", "stage='/tmp/p35-p56-'+stamp[9:15];directory='/run/p42-000043/data'")
    text=sub(text,'duration=630000 if args.long else 85000;seconds=45 if args.long else 12;cycles=4 if args.long else 1',
        "duration=900000;seconds=12;cycles=1\n    if args.long:raise ValueError('attach trial has three bounded 12-second sources only')")
    text=sub(text,"('p56-live-'+stamp)","('p57-live-'+stamp)")
    insert="    def save():write(out/'report.json',r)"
    text=sub(text,insert,"    r.update(startup_profile='p57',boot_report="+repr(rel(args.boot))+",boot_report_sha256="+repr(sha(args.boot))+
        ",clock_readback="+repr(rel(args.clock))+",clock_readback_sha256="+repr(sha(args.clock))+
        ",host_launches_RX=False,calibration_uses_new_boot=True,persistent_AI_default=True)\n"+insert)
    text=sub(text,"        idle_rx()\n        if digest(rx,'/etc/rcS.d/S99board')!=sha(ROOT/'board/boot/S99board'):raise ValueError('startup must be paused before experiment')",
        "        if rx.value('/proc/sys/kernel/random/boot_id')!=r['expected_boot'] or rx.value('/proc/sys/kernel/tainted')!='0':raise ValueError('RX identity changed')\n"
        "        if digest(rx,'/etc/rcS.d/S99board')!="+repr(boot['installed_files_sha256']['boot'])+":raise ValueError('P57 startup selection changed')\n"
        "        if digest(rx,"+repr(boot['installed_directory']+'/control')+")!="+repr(boot['installed_files_sha256']['control'])+":raise ValueError('owned control changed')")
    start=text.index("        r['initial_TX_inspection']=tx_idle();r['resolved_RAM_tmp']=board_ram_tmp(rx);save()")
    end=text.index("        first=wait_for(",start)
    text=text[:start]+"""        r['initial_TX_inspection']=tx_idle();r['resolved_RAM_tmp']=board_ram_tmp(rx);save()
        rx.command('mkdir '+stage);rx.command('s='+stage)
        rx.command('j='+"""+repr(boot['installed_directory'])+""")
        rx.command('o=/run/p42-000043/data');rx.command('h=/run/p42-000043/shot')
        rx.command('test ! -e /run/p42-000043/exit')
        pid=int(rx.value('/run/p42-000043/pid'));r['owned_timeout_pid']=pid;rx_running=True
        r['status']='attached_to_board_started_RX_waiting_calibration';save()
"""+text[end:]
    text=sub(text,"rx.command('echo '+str(shot)+' >$s/shot')","rx.command('echo '+str(shot)+' >$h')")
    start=text.index("        rx.command('b='+r['expected_boot'])")
    end=text.index("        case=start_tx('tone',15)",start)
    text=text[:start]+"        rx.command('k='+token);rx.command('sh $j/control calibrate $k')\n        wait_for(lambda a:a['state']=='WAIT_PILOT',8)\n"+text[end:]
    start=text.index('        # Keep the same RX context running to its predeclared duration.')
    end=text.index("        r['native_summary']=",start)
    text=text[:start]+"""        r['status']='final_source_off_six_second_hold';save()
        held=time.monotonic()
        while time.monotonic()-held<6:
            sample();time.sleep(.5)
        r['status']='known_cases_complete_owned_stop';save()
        rx.command('sh $j/control stop',timeout=12);rx_running=False
        wait_for(lambda a:a['state']=='STOPPED',5)
        r['launcher_exit']=rx.value('/run/p42-000043/exit')
        if r['launcher_exit'] not in ('0','143'):raise ValueError('owned RX completion unconfirmed')
"""+text[end:]
    text=sub(text,"s['status']!='pass' or s['reason']!='duration_complete'", "s['status']!='stopped' or s['reason']!='signal_requested_stop'")
    text=sub(text,"rx.command('kill -TERM '+str(pid));rx.command('wait '+str(pid)+'; echo owned_wait_rc=$?',timeout=12)",
        "rx.command('sh $j/control stop',timeout=12)")
    review=(ROOT/'experiments/p56_review_trial.py').read_text(encoding='utf-8')
    review=sub(review,'import argparse,json,collections','import argparse,json,collections\nimport sys\nsys.path.insert(0,'+repr(str(ROOT/'experiments'))+')')
    review=sub(review,"strftime('p56-review-%Y%m%dT%H%M%SZ')","strftime('p57-review-%Y%m%dT%H%M%SZ')")
    review=sub(review,"check('requested session duration reached',t['native_summary']['elapsed_software_s']>=t['duration_ms']/1000 and t['native_summary']['worker_started'] and t['native_summary']['worker_joined'])",
        "check('board-started session owned stop',t.get('host_launches_RX') is False and t['native_summary']['reason']=='signal_requested_stop' and t['native_summary']['status']=='stopped' and t['native_summary']['elapsed_software_s']>=55 and t['native_summary']['worker_started'] and t['native_summary']['worker_joined'])")
    review=sub(review,"ten_minute_duration_verified=t['duration_ms']>=600000", "ten_minute_duration_verified=t['native_summary']['elapsed_software_s']>=600,board_started_RX=True,boot_report=t['boot_report'],boot_report_sha256=t['boot_report_sha256']")
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p57-attachment-%Y%m%dT%H%M%SZ');out.mkdir()
    controller=out/'controller.py';reviewer=out/'review.py';controller.write_text(text,encoding='utf-8');reviewer.write_text(review,encoding='utf-8')
    compile(text,str(controller),'exec');compile(review,str(reviewer),'exec')
    r=dict(status='prepared_board_owned_RX_calibration_and_three_class_controller',board_operations=False,
        inputs={name:dict(path=rel(path),sha256=sha(path)) for name,path in dict(boot=args.boot,clock=args.clock,source=args.source,
            parent=parent,parent_review=ROOT/'experiments/p56_review_trial.py',generator=Path(__file__)).items()},
        controller=rel(controller),controller_sha256=sha(controller),reviewer=rel(reviewer),reviewer_sha256=sha(reviewer),
        host_launches_RX=False,TX_seconds_per_case=12,pilot_seconds=15,policy='results/p56-policy-20261024T085402Z/report.json')
    write(out/'report.json',r);print(out);print(r['status'])
if __name__=='__main__':main()
