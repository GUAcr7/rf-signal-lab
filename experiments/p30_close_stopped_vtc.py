"""Close a deliberately stopped off-target long simulation without a pass claim."""
from datetime import datetime,timezone
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]


def main():
    folder=ROOT/'results/p30-vtc-test-20261019T095520Z'
    path=folder/'report.json'
    report=json.loads(path.read_text('utf-8'))
    if report['status']!='running':raise RuntimeError('expected stopped, formerly running simulation')
    shutil.copy2(path,folder/'report-before-stop.json')
    report.update(status='stopped_without_acceptance',ended_utc=datetime.now(timezone.utc).isoformat(),
        reason='Controlled termination of this experiment process tree. Re-scoped to the actual 800x480 carrier panel after retaining original vendor timing; no 1080p full-frame result.',
        terminated_root_pid=34988,hardware_operations=False)
    path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(path)


if __name__=='__main__':main()
