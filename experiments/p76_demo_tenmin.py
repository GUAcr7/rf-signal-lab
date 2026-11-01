"""Verify installed autonomous app with fixed-entry RF and >=630s session.

No host RX start/restart, no PL reload, no second reboot; TX remains bounded.
"""
import argparse,json,time
from datetime import datetime,timezone
from pathlib import Path
from types import SimpleNamespace
from p45_checkpoint import ROOT,read,write,sha,rel
from p67_board_trial import control
from p68_evidence import archive
from p52_ram import board_ram_tmp
from rfsig.board_session import WORK,require_rx_control,require_tx_off,one_json


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--boot',required=True,type=Path);a=ap.parse_args()
    boot=read(a.boot)
    if boot['status']!='passed_P76_warm_boot_autonomous_phase_AI_display':raise ValueError('verified installed P76 required')
    human=ROOT/'results/p68-link-20261026.json';link=read(human)
    if not link['unchanged_TX1_attenuation_RX1A']:raise ValueError('established RF link required')
    with control.operation_lock():
        c=control.Controller('p76-demo');print(c.out,flush=True)
        r=c.record;r.update(status='P76_demo_preflight',boot=rel(a.boot),boot_sha256=sha(a.boot),steps=[],polls=[],chunks=[],
            protocol=dict(minimum_software_elapsed_s=630,source_seconds=30,pilot_seconds=15,
                stable_after_first_observation_s=2,stable_end_margin_s=3,minimum_coverage=.70,minimum_conditional_accuracy=.90,
                source_seed=2026102315,scope='known controlled competition demo, no new independent accuracy'),
            host_RX_starts=0,true_power_cycle_verified=False,link_confirmation=rel(human),link_confirmation_sha256=sha(human))
        (c.out/'executed-demo.py').write_bytes(Path(__file__).read_bytes());c.save()
        def run(action,signal='tone',seconds=15):
            child=control.Controller(action)
            child.options=SimpleNamespace(rf_link_reviewed=True,signal=signal,seconds=seconds)
            try:
                child.action(action);control.finish_record(child,True)
            except Exception as exc:
                control.finish_record(child,False,exc);raise
            r['steps'].append(dict(action=action,signal=signal,seconds=seconds,report=rel(child.out/'report.json'),
                                   report_sha256=sha(child.out/'report.json')));c.save()
            return child
        try:
            c.status();initial=r['boards']['RX'];require_rx_control(initial,running=True);require_tx_off(r['boards']['TX'])
            if c.profile['schema']!='rfsig.receiver_profile.p76.v1' or initial['boot_id']!=boot['expected_boot']:
                raise ValueError('installed boot/profile changed')
            r.update(expected_boot=initial['boot_id'],initial_RX=initial,initial_TX=r['boards']['TX']);c.save()
            run('prepare-source');run('calibrate')
            for signal,seconds in [('tone',15),('bpsk',30),('qpsk',30),('qam16',30)]:
                print('P76 controlled RF '+signal+' '+str(seconds)+'s',flush=True);run('send',signal,seconds)
            r['status']='P76_observing_autonomous_10min';c.save()
            with c.board('RX') as (b,identity):
                last=-1;end=time.monotonic()+950
                while time.monotonic()<end:
                    p=one_json(c.optional(b,WORK+'/data/progress.json'))
                    ai=one_json(c.optional(b,WORK+'/data/ai.json'));metric=one_json(c.optional(b,WORK+'/data/metrics.json'))
                    r['polls'].append(dict(progress=p,AI=ai,metrics=metric));c.save()
                    print('P76 autonomous '+str(round(p['elapsed_software_s']))+'s updates='+str(p['display_updates']),flush=True)
                    if p['elapsed_software_s']>=630:break
                    if p['state']!='running' or p['display_updates']<=last or not ai['ready']:
                        raise ValueError('autonomous receiver stopped/stalled/lost calibration')
                    last=p['display_updates'];time.sleep(20)
                else:raise TimeoutError('ten-minute session observation deadline')
                if b.value('/proc/sys/kernel/random/boot_id')!=r['expected_boot']:raise ValueError('unexpected reboot')
            run('stop');c.status()
            require_rx_control(r['boards']['RX'],running=False);require_tx_off(r['boards']['TX'])
            r.update(after_RX=r['boards']['RX'],after_TX=r['boards']['TX'],RX_stopped=True,TX_stopped=True,status='P76_archiving_10min_session');c.save()
            with c.board('RX') as (b,identity):
                if b.value('/proc/sys/kernel/random/boot_id')!=r['expected_boot']:raise ValueError('archive boot differs')
                r['RAM_tmp']=board_ram_tmp(b)
                stage='/tmp/p35-p76-'+datetime.now(timezone.utc).strftime('%H%M%S');r['archive_stage']=stage;c.save()
                b.command('s='+stage);b.command('test ! -e $s');b.command('mkdir $s');b.command('mkdir $s/data');b.command('w='+WORK)
                names=('ai.json','ai-history.jsonl','metrics.json','metrics-history.jsonl','summary.json','progress.json','last-display-packed.bin','fb.raw')
                for name in names:b.command('cp $w/data/'+name+' $s/data/'+name)
                archive(c,b,stage,names)
            files=c.out/'files';rows=[json.loads(s) for s in (files/'ai-history.jsonl').read_text().splitlines()]
            metrics=[json.loads(s) for s in (files/'metrics-history.jsonl').read_text().splitlines()];summary=read(files/'summary.json')
            if (summary['elapsed_software_s']<630 or summary['display_revision']!='p75'
                or summary['reason']!='signal_requested_stop' or summary['status']!='stopped'
                or len(rows)!=summary['display_updates']+1 or len(metrics)!=len(rows)
                or not all(summary[k] for k in ('worker_joined','buffer_released','context_released','RF_after_matches'))
                or rows[-1]['state']!='STOPPED' or metrics[-1]['valid']):raise ValueError('full session/cleanup invalid')
            groups=[]
            for item in r['steps']:
                if item['action']!='send':continue
                p=ROOT/item['report'];s=read(p)
                if sha(p)!=item['report_sha256'] or not s['TX_cleanup_verified']:raise ValueError('RF source evidence differs')
                anchor=s['AI_observations'][0]['elapsed_s']
                selected=[x for x in rows[:-1] if anchor+2<=x['elapsed_s']<=anchor+item['seconds']-3]
                accepted=[x for x in selected if x['accepted_class']>=0]
                expected={'bpsk':0,'qpsk':1,'qam16':2}.get(item['signal'],-1)
                correct=sum(x['accepted_class']==expected for x in accepted)
                coverage=len(accepted)/len(selected) if selected else 0
                accuracy=correct/len(accepted) if accepted else 0
                ok=(len(selected)>=5 and (all(x['state']=='UNSUPPORTED_TONE' for x in selected) if expected<0 else coverage>=.7 and accuracy>=.9))
                groups.append(dict(source=item['signal'],updates=len(selected),accepted=len(accepted),correct=correct,
                                   coverage=coverage,conditional_accuracy=accuracy,passed=ok))
            times=[x['elapsed_s'] for x in rows[:-1]];sequences=[x['source_block_sequence'] for x in rows[:-1]]
            gaps=[v-u for u,v in zip(times,times[1:])]
            if (any(v<=u for u,v in zip(sequences,sequences[1:])) or not gaps or max(gaps)>=2
                or not all(g['passed'] for g in groups) or len(groups)!=4
                or any(x['boot_id']!=r['expected_boot'] for x in rows)
                or any(x['source_block_sequence']!=m['source_block_sequence'] or x['state']!=m['AI_state'] for x,m in zip(rows,metrics))):
                r['groups']=groups;raise ValueError('full-history RF/UI gate failed')
            r.update(status='passed_P76_installed_autonomous_10min_RF_full_history_stopped',groups=groups,
                     elapsed_software_s=summary['elapsed_software_s'],display_updates=summary['display_updates'],maximum_update_interval_s=max(gaps),
                     ten_minute_session_verified=True,physical_LCD_confirmed=False,source_OFF_after_test=True)
        except Exception as exc:
            r.update(status='failed_or_unconfirmed_P76_demo',error=repr(exc));c.save()
            try:
                run('stop');c.status();r['failure_final_boards']=r['boards']
            except Exception as stop_error:r['cleanup_error']=repr(stop_error)
        finally:r['serial_closed']=True;c.save()
        print(c.out);print(r['status'],flush=True)


if __name__=='__main__':main()
