"""User power-cycle proof and >=630s autonomous RX; no host RX start or TX."""
import json,re,time
from datetime import datetime,timezone
from pathlib import Path
from p45_checkpoint import ROOT,read,write,sha,rel
from p67_board_trial import control
from p70_cold_prepare import passive_startup_ready
from p68_evidence import archive
from p52_ram import board_ram_tmp
from rfsig.board_session import WORK,require_rx_control,require_tx_off,one_json

def main():
    human=ROOT/'results/p71-user-power-cycle-20261026.json';event=read(human)
    passive=ROOT/event['passive'];p=read(passive);halt=ROOT/event['requested_halt'];h=read(halt)
    folder=passive.parent;text=(folder/'console.txt').read_text(encoding='utf-8')
    raw=(folder/'uart.rx.bin').read_bytes().decode('ascii',errors='replace')
    if (not event['new_board_powercycled_by_user'] or event['host_reboot_substituted']
        or not h['halt_observed'] or sha(halt)!=p['halt_sha256'] or not p['serial_closed']
        or (folder/'uart.tx.bin').read_bytes()!=b'' or p['UART_bytes_sent']!=0
        or not passive_startup_ready(raw) or not passive_startup_ready(text)):
        raise ValueError('human, prior halt and passive zero-write startup proof required')
    ids=re.findall(r'ORIGINAL_BACKUP_VERIFIED boot=([0-9a-f-]{36})',raw)
    if len(ids)!=1 or ids[0]==h['expected_boot'] or event['old_boot']!=h['expected_boot']:raise ValueError('new boot identity proof differs')
    with control.operation_lock():
        c=control.Controller('p71-cold');print(c.out,flush=True)
        c.record.update(status='P71_cold_preflight',human=rel(human),human_sha256=sha(human),passive=rel(passive),
            passive_sha256=sha(passive),passive_console_sha256=sha(folder/'console.txt'),passive_RX_sha256=sha(folder/'uart.rx.bin'),
            passive_TX_sha256=sha(folder/'uart.tx.bin'),halt=rel(halt),halt_sha256=sha(halt),
            expected_boot=ids[0],old_boot=h['expected_boot'],host_RX_starts=0,reboots_issued=0,RF_transmissions=0,
            true_power_cycle_verified=False,ten_minute_duration_verified=False,polls=[],chunks=[],serial_closed=False,
            passive_watcher_status=p['status'],watcher_false_negative_due_to_auto_login=True)
        original_save=c.save
        def save():
            original_save();write(ROOT/'results/p71-active.json',dict(status=c.record['status'],report=rel(c.out/'report.json'),
                report_sha256=sha(c.out/'report.json'),true_power_cycle_verified=c.record['true_power_cycle_verified'],
                ten_minute_duration_verified=c.record['ten_minute_duration_verified'],serial_closed=c.record['serial_closed']))
        c.save=save;(c.out/'executed-cold-verify.py').write_bytes(Path(__file__).read_bytes());c.save()
        try:
            c.status();rx=c.record['boards']['RX'];tx=c.record['boards']['TX'];require_tx_off(tx)
            if rx['boot_id']!=ids[0] or c.profile.get('schema')!='rfsig.receiver_profile.p70.v1':raise ValueError('current cold/profile identity differs')
            if rx['session_state'] not in ('RUNNING','RUNNING_PROGRESS_UNCONFIRMED','STOPPED'):raise ValueError('RX state inconsistent')
            c.record.update(initial_RX=rx,initial_TX=tx,true_power_cycle_verified=True,status='P71_cold_observing_autonomous_RX')
            c.save()
            with c.board('RX') as (b,identity):
                startup=one_json(c.optional(b,WORK+'/data/metrics.json'))
                c.record['initial_metrics']=startup
                if rx['session_state']!='STOPPED' and (rx['AI']['state']!='CALIBRATION_REQUIRED' or rx['AI']['ready'] or startup['valid']):raise ValueError('stale startup calibration/metric')
                deadline=time.monotonic()+950;last=-1
                while time.monotonic()<deadline:
                    progress=one_json(c.optional(b,WORK+'/data/progress.json'))
                    ai=one_json(c.optional(b,WORK+'/data/ai.json'))
                    m=one_json(c.optional(b,WORK+'/data/metrics.json'))
                    c.record['polls'].append(dict(progress=progress,AI=ai,metrics=m));c.save()
                    print('P71 autonomous RX '+str(round(progress['elapsed_software_s']))+'s updates='+str(progress['display_updates']),flush=True)
                    if progress['elapsed_software_s']>=630:break
                    if progress['state']!='running' or progress['display_updates']<=last or ai['state']!='CALIBRATION_REQUIRED' or m['valid']:raise ValueError('premature stop, stalled UI or stale calibration')
                    last=progress['display_updates'];time.sleep(20)
                else:raise TimeoutError('ten minute observation deadline')
                if b.value('/proc/sys/kernel/random/boot_id')!=ids[0]:raise ValueError('reboot during observation')
            c.action('stop')
            # action() retains its pre-action boards snapshot and writes
            # after_RX separately. Refresh before asserting current stopped.
            c.status()
            require_rx_control(c.record['boards']['RX'],running=False);require_tx_off(c.record['boards']['TX'])
            c.record.update(after_RX=c.record['boards']['RX'],after_TX=c.record['boards']['TX'],status='P71_stopped_archiving_cold_RX');c.save()
            with c.board('RX') as (b,identity):
                current=c.inspect('RX',b,identity);require_rx_control(current,running=False)
                if current['boot_id']!=ids[0]:raise ValueError('archive boot changed')
                c.record['RAM_tmp']=board_ram_tmp(b);stage='/tmp/p35-p71-'+datetime.now(timezone.utc).strftime('%H%M%S')
                b.command('s='+stage);b.command('test ! -e $s');b.command('mkdir $s');b.command('mkdir $s/data');b.command('w='+WORK)
                names=('ai.json','ai-history.jsonl','metrics.json','metrics-history.jsonl','summary.json','progress.json','last-display-packed.bin','fb.raw')
                for name in names:b.command('cp $w/data/'+name+' $s/data/'+name)
                archive(c,b,stage,names)
            files=c.out/'files';rows=[json.loads(s) for s in (files/'ai-history.jsonl').read_text().splitlines()]
            metrics=[json.loads(s) for s in (files/'metrics-history.jsonl').read_text().splitlines()];summary=read(files/'summary.json')
            if (len(rows)!=summary['display_updates']+1 or len(metrics)!=len(rows) or summary['elapsed_software_s']<630
                or not all(summary[k] for k in ('worker_joined','buffer_released','context_released','RF_after_matches'))
                or any(v['boot_id']!=ids[0] or v['state']!='CALIBRATION_REQUIRED' or v['ready'] or v['accepted_class']!=-1 for v in rows[:-1])
                or rows[-1]['state']!='STOPPED' or any(v['valid'] for v in metrics)):
                raise ValueError('full cold session history/cleanup failed')
            sequences=[v['source_block_sequence'] for v in rows[:-1]]
            times=[v['elapsed_s'] for v in rows[:-1]]
            gaps=[b-a for a,b in zip(times,times[1:])]
            if any(b<=a for a,b in zip(sequences,sequences[1:])) or max(gaps)>=2:raise ValueError('cold UI source/interval regression')
            if any(m['source_block_sequence']!=a['source_block_sequence'] for m,a in zip(metrics,rows)):raise ValueError('cold metrics/AI block mismatch')
            c.record.update(status='passed_P71_user_cold_autonomous_ROI_10min_RX_stopped',ten_minute_duration_verified=True,
                display_updates=summary['display_updates'],elapsed_software_s=summary['elapsed_software_s'],maximum_update_interval_s=max(gaps),
                RX_stopped=True,TX_stopped=True,physical_LCD_confirmation='pending',
                AI_regression_issue_16QAM_still_open=True)
        except Exception as e:
            c.record.update(status='failed_or_unconfirmed_P71_cold',error=repr(e));c.save()
            try:c.action('stop');c.record['failure_stop_attempted']=True
            except Exception as cleanup:c.record['cleanup_error']=repr(cleanup)
        c.record['serial_closed']=True;c.save();print(c.record['status'],flush=True)
        return int(not c.record['status'].startswith('passed'))
if __name__=='__main__':raise SystemExit(main())
