"""Save the user's end-of-day checkpoint and flush both idle boards; no shutdown."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
from p26_retrieve_chunks import ChunkConsole, ROOT


def main():
    evidence=ROOT/'results/p31-end-state-20261019T145901Z/report.json'
    measured=json.loads(evidence.read_text('utf-8'))
    if measured['status']!='recovered_original_RF_both_boards_idle_and_guard_verified':
        raise RuntimeError('final idle-state check required')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out=ROOT/'results'/('session-stop-'+stamp)
    out.mkdir(exist_ok=False)
    record=dict(status='saving',stages=[],idle_state=str(evidence),
        requested_by_user=True,RF_operations=False,board_shutdown_issued=False,
        boards={},next_session_requires_new_identity_check=True)

    def save():
        (out/'report.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')

    board=None
    save()
    try:
        for port,identity in [('COM9','Linux pzp201'),('COM8','Zynq-Tronlong')]:
            board=ChunkConsole(port,record,save)
            if identity not in board.command('uname -a'):
                raise RuntimeError('unexpected board '+port)
            expected=measured['boards'][port]['boot_id']
            if expected not in board.command('cat /proc/sys/kernel/random/boot_id'):
                raise RuntimeError('board changed since idle check '+port)
            board.command('sync',timeout=20)
            record['boards'][port]=dict(last_boot_id=expected,sync_completed=True)
            board.close();board=None
        record['status']='records_saved_both_idle_boards_synced_no_shutdown'
    except Exception as error:
        record.update(status='records_saved_board_sync_incomplete',error=repr(error))
    finally:
        if board:
            board.close()
        record['serial_handles_closed']=True
        save()
    for name in ['START-HERE.md','TX-SOURCE-STATUS.json','docs/handoff/RESUME-20261019.md']:
        target=out/'before'/name
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(ROOT/name,target)
    state_path=ROOT/'TX-SOURCE-STATUS.json'
    state=json.loads(state_path.read_text('utf-8'))
    state['session_stop']=dict(date_local='2026-10-19',timezone='Asia/Shanghai',
        user_requested_stop=True,record=str(out.relative_to(ROOT)/'report.json').replace('\\','/'),
        last_idle_evidence=str(evidence.relative_to(ROOT)).replace('\\','/'),
        board_sync_complete=all(record['boards'].get(p,{}).get('sync_completed') for p in ['COM8','COM9']),
        board_shutdown_issued=False,boot_ids_are_last_observed_not_next_boot=True,
        next_start='Read START-HERE.md; enumerate/identify boards and new boot IDs; restore RAM tools and reviewed RX profile before experiments')
    state_path.write_text(json.dumps(state,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    record['status_file_sha256']=hashlib.sha256(state_path.read_bytes()).hexdigest()
    save()
    print(out)
    print(record['status'])


if __name__=='__main__':main()
