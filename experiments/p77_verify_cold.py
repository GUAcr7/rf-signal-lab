"""Read-only confirmation after the user's real power cycle; no new RX or TX.

Warm eleven-minute/RF proof stays immutable; cold evidence is a separate record.
"""
import argparse,re,time
from pathlib import Path
from p45_checkpoint import ROOT,read,write,sha,rel
from p67_board_trial import control
from p70_cold_prepare import passive_startup_ready
from rfsig.board_session import WORK,require_rx_control,require_tx_off,one_json


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--human',type=Path,required=True);a=ap.parse_args()
    human=read(a.human);passive_path=ROOT/human['passive'];p=read(passive_path)
    halt_path=ROOT/human['requested_halt'];halt=read(halt_path)
    raw=passive_path.parent/'uart.rx.bin';sent=passive_path.parent/'uart.tx.bin'
    text=raw.read_bytes().decode('ascii',errors='replace')
    if (not human['new_board_powercycled_by_user'] or human['host_reboot_substituted']
        or not human['screen_lit_dynamic_confirmed'] or not halt['halt_observed']
        or sha(halt_path)!=p['halt_sha256'] or not p['serial_closed'] or p['listening']
        or p['status']!='captured_P76_new_kernel_autonomous_ready_zero_writes'
        or p['UART_bytes_sent']!=0 or sent.read_bytes()!=b'' or not passive_startup_ready(text)):
        raise ValueError('actual user cycle plus completed zero-write passive startup required')
    ids=re.findall(r'ORIGINAL_BACKUP_VERIFIED boot=([0-9a-f-]{36})',text)
    if len(ids)!=1 or ids[0]==halt['expected_boot'] or halt['expected_boot']!=human['old_boot']:
        raise ValueError('new passive boot identity differs')
    with control.operation_lock():
        c=control.Controller('p77-cold');r=c.record;print(c.out,flush=True)
        r.update(status='P77_cold_read_only_preflight',human=rel(a.human),human_sha256=sha(a.human),
            passive=rel(passive_path),passive_sha256=sha(passive_path),passive_RX_sha256=sha(raw),passive_TX_sha256=sha(sent),
            halt=rel(halt_path),halt_sha256=sha(halt_path),old_boot=human['old_boot'],expected_boot=ids[0],
            host_RX_starts=0,RF_transmissions=0,reboots_issued=0,physical_LCD_confirmed=True,
            true_power_cycle_verified=False,polls=[])
        (c.out/'executed-cold.py').write_bytes(Path(__file__).read_bytes());c.save()
        try:
            c.status();rx=r['boards']['RX'];require_rx_control(rx,running=True);require_tx_off(r['boards']['TX'])
            if c.profile.get('schema')!='rfsig.receiver_profile.p76.v1' or rx['boot_id']!=ids[0]:
                raise ValueError('cold receiver does not match installed P76/new boot')
            r.update(selected_boot=r['provenance']['accepted_boot_report'],
                     selected_boot_sha256=r['provenance']['accepted_boot_report_sha256'],initial_RX=rx,initial_TX=r['boards']['TX'])
            with c.board('RX') as (b,identity):
                if b.value('/run/p43-init-boot')!=ids[0]:raise ValueError('cold board-init marker absent')
                log=b.command('cat /run/p43-boot.log');r['cold_startup_log']=log
                (c.out/'cold-startup-log.txt').write_text(log,encoding='utf-8')
                for marker in ('ORIGINAL_BACKUP_VERIFIED','EMPTY_BINDINGS_VERIFIED','PL_ATTEMPT=1','OVERLAY_ATTEMPT=1','MONITOR_LAUNCH','PERSISTENT_MONITOR_READY'):
                    if len(re.findall(r'^p43: '+re.escape(marker)+r'(?:\s|\r?$)',log,re.M))!=1:
                        raise ValueError('cold startup marker '+marker)
                if 'FAILED:' in log:raise ValueError('cold startup failure')
                if c.digest(b,WORK+'/monitor')!=c.profile['binary_sha256']:raise ValueError('wrong running monitor')
                processes=b.command('for n in /proc/[0-9]*/exe;do readlink $n || :;done')
                count=sum(line.strip()==WORK+'/monitor' for line in processes.splitlines())
                if count!=1:raise ValueError('expected exactly one monitor executable')
                r['monitor_process_count']=count
                previous=-1
                for index in range(3):
                    for attempt in range(5):
                        ai=one_json(c.optional(b,WORK+'/data/ai.json'))
                        metric=one_json(c.optional(b,WORK+'/data/metrics.json'))
                        if ai['source_block_sequence']==metric['source_block_sequence']:break
                    else:raise ValueError('no coherent AI/metric pair')
                    progress=one_json(c.optional(b,WORK+'/data/progress.json'))
                    if (ai['boot_id']!=ids[0] or ai['state']!='CALIBRATION_REQUIRED' or ai['ready']
                        or ai['accepted_class']!=-1 or ai['calibration_token'] or metric['valid']
                        or any(metric[k] is not None for k in ('LO_plus_center_hz','ROI_99_width_hz','ROI_power_counts_squared','center_offset_hz'))
                        or progress['state']!='running' or progress['display_updates']<=previous):
                        raise ValueError('stale calibration/metrics or stalled autonomous display')
                    r['polls'].append(dict(AI=ai,metrics=metric,progress=progress));previous=progress['display_updates'];c.save()
                    if index<2:time.sleep(2)
                ending=c.inspect('RX',b,identity);require_rx_control(ending,running=True)
                if ending['boot_id']!=ids[0]:raise ValueError('boot changed during cold confirmation')
                r['after_RX']=ending
            r.update(status='passed_P77_user_real_power_cycle_P76_autonomous_fresh_AI_display',
                true_power_cycle_verified=True,RX_running=True,RX_halted=False,TX_stopped=True,
                physical_LCD_confirmed=True,serial_closed=True,persistent_configuration_changed=False,
                scope='actual cold startup and fresh advancing display; prior P76 eleven-minute RF proof remains separate',
                autonomous_duration_s_observed=r['polls'][-1]['progress']['elapsed_software_s'],
                display_updates_observed=r['polls'][-1]['progress']['display_updates'])
        except Exception as exc:r.update(status='failed_or_unconfirmed_P77_cold_check',error=repr(exc))
        finally:r['serial_closed']=True;c.save()
        print(c.out);print(r['status'],flush=True)


if __name__=='__main__':main()
