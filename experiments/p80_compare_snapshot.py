"""Compare old/new complete RX checks read-only, no RF or firmware changes."""
from pathlib import Path
from datetime import datetime,timezone
import sys,json,time
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'host'),str(ROOT/'src'),str(ROOT/'experiments')]
from p201_usb_network import PanelController
from fast_panel_control import FastPanelController
import board_control as control

def main():
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p80-snapshot-compare-%Y%m%dT%H%M%SZ');out.mkdir()
    r=dict(status='comparing',RF_transmissions=0,PL_changes=False,reads=[])
    with control.operation_lock():
        try:
            for cls in (PanelController,FastPanelController,FastPanelController):
                c=cls('p80-snapshot-read');print(c.out,flush=True);start=time.monotonic()
                try:
                    c.status();c.record['status']='passed_P80_readonly_snapshot'
                except Exception as error:
                    c.record.update(status='failed_P80_readonly_snapshot',error=repr(error));raise
                finally:c.record['serial_closed']=True;c.save()
                elapsed=time.monotonic()-start
                r['reads'].append(dict(kind=cls.__name__,seconds=elapsed,report=str((c.out/'report.json').relative_to(ROOT)),
                                       sha256=control.sha(c.out/'report.json'),RX=c.record['boards']['RX']))
            old=r['reads'][0]['RX'];r['equivalent_keys']=[]
            keys=('boot_id','taint','IIO_names','RF','RF_matches','RX_buffer','TX_buffer','RX_scans','profile_hashes','profile_verified',
                  'selected_wrapper_sha256','owned_timeout_pid','owned_timeout_argv','init_boot_marker','AI','progress','later_progress','summary','session_state','critical_kernel_fault')
            for key in keys:
                if not all(x['RX'][key]==old[key] for x in r['reads'][1:]):raise ValueError('Snapshot mismatch: '+key)
                r['equivalent_keys'].append(key)
            r['status']='passed_P80_complete_stopped_snapshot_equivalence'
        except Exception as error:r.update(status='failed_or_incomplete_P80_snapshot_compare',error=repr(error))
        (out/'report.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(out,flush=True);print(r['status'],flush=True)
    return 0 if r['status'].startswith('passed_') else 1

if __name__=='__main__':raise SystemExit(main())
