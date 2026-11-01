"""Existing fixed stop/start/new-background operations, no RF transmission."""
from pathlib import Path
from datetime import datetime,timezone
import json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'host'),str(ROOT/'src'),str(ROOT/'experiments')]
import board_control as control

def main():
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p79-prepare-session-%Y%m%dT%H%M%SZ');out.mkdir()
    r=dict(status='preparing_P79_new_RX_background',steps=[],RF_transmissions=0)
    def save():(out/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    with control.operation_lock():
        try:
            for action in ('stop','start','calibrate'):
                c=control.Controller(action);print(c.out,flush=True)
                try:c.action(action)
                except Exception as error:control.finish_record(c,False,error);raise
                else:control.finish_record(c,True)
                r['steps'].append(dict(action=action,report=str((c.out/'report.json').relative_to(ROOT)),sha256=control.sha(c.out/'report.json')));save()
            r['status']='passed_P79_new_RX_waiting_reference_tone'
        except Exception as error:r.update(status='failed_P79_session_prepare',error=repr(error))
        finally:save();print(out,flush=True);print(r['status'],flush=True)
    return 0 if r['status'].startswith('passed_') else 1

if __name__=='__main__':raise SystemExit(main())
