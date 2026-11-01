"""One 8s reference tone, STOP 2s after native submission. Original coax only."""
from pathlib import Path
from datetime import datetime,timezone
import json,argparse
import queue
import sys
import threading
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'host'),str(ROOT/'src'),str(ROOT/'experiments')]
import source_screen_rf as panel

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--natural',action='store_true');ap.add_argument('--seconds',type=int,default=8);args=ap.parse_args()
    panel.validate_request('tone',args.seconds)
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p79-cancel-trial-%Y%m%dT%H%M%SZ');out.mkdir()
    stop=threading.Event();events=queue.Queue();finished=threading.Event()
    record=dict(status='running_P79_owned_guard_stop',requested_seconds=args.seconds,stop_after_submission_s=None if args.natural else 2,
                RF_link_confirmed_by_user='2026-10-27 original TX1/attenuation/RX1A unchanged',screen_touches=False)
    (out/'executed.py').write_bytes(Path(__file__).read_bytes())
    def watch():
        while not finished.is_set():
            try:message=events.get(timeout=.1)
            except queue.Empty:continue
            if message['kind']=='submitted':
                record['submission_seen_monotonic']=time.monotonic()
                if not args.natural and not finished.wait(2):
                    record['cancel_monotonic']=time.monotonic();stop.set()
                return
    with panel.control.operation_lock():
        worker=threading.Thread(target=watch,daemon=True);worker.start()
        try:
            result=panel.job('run','tone',args.seconds,stop,events)
            record['job']=result
            path=ROOT/result['report'];record['job_sha256']=panel.control.sha(path)
            evidence=json.loads(path.read_text('utf-8'))
            record['checks']=dict(job_passed=result['passed'],actual_stop=result.get('cancelled') is (not args.natural),
                                  native_cleanup=evidence.get('TX_cleanup_verified') is True,
                                  stop_signal_native=('stop_signal=0' if args.natural else 'stop_signal=1') in evidence.get('TX_transcript',''),
                                  current_TX_idle=evidence.get('after_TX',{}).get('TX_buffer')=='0')
            record['status']=('passed_P79_real_guard_natural_deadline' if args.natural else 'passed_P79_real_owned_guard_stop') if all(record['checks'].values()) else 'failed_or_unconfirmed_P79_real_stop'
        finally:
            finished.set();worker.join(timeout=1)
            (out/'report.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            print(out,flush=True);print(record['status'],flush=True)
    return 0 if record['status'].startswith('passed_') else 1

if __name__=='__main__':raise SystemExit(main())
