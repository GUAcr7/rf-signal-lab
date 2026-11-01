"""Snapshot this installation attempt; never infer feature success from download."""
from collections import deque
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASE = Path('E:/FPGA_Tools/Downloads/NetFx3-System-20261025T121739Z')


def main():
    out = ROOT / 'results' / datetime.now(timezone.utc).strftime('p65-environment-%Y%m%dT%H%M%SZ')
    out.mkdir(exist_ok=False)
    source = BASE / 'source/Microsoft-Windows-NetFx3-OnDemand-Package~31bf3856ad364e35~amd64~~.cab'
    wanted = 'dc3af93af5c64dc115409437d31018baf2c3c46167806a599124bc905ae512f6'
    actual = hashlib.sha256(source.read_bytes()).hexdigest()
    if actual != wanted or source.stat().st_size != 71321276:
        raise ValueError('Matching source missing or changed')
    for name, path in {
        'cache-copy-report.json': BASE / 'source/cache-copy-report.json',
        'online-attempt-report.json': ROOT / 'results/p65-netfx3-system-retry-20261025T121739Z/report.json',
        'dism.log': BASE / 'dism.log',
    }.items():
        (out / name).write_bytes(path.read_bytes())
    selected = deque(maxlen=90)
    with Path('C:/Windows/Logs/CBS/CBS.log').open('r', errors='replace') as stream:
        for line in stream:
            if any(term in line for term in ('NetFx3', 'NetFX3', 'WULib DownloadProgress', 'CBS_E_CANCEL', 'DWLD:')):
                selected.append(line)
    (out / 'CBS-selected.log').write_text(''.join(selected), encoding='utf-8')
    command = "Get-CimInstance Win32_Process -Filter \"Name='dism.exe'\" | Select-Object Name,ProcessId,CreationDate | ConvertTo-Json -Compress"
    proc = subprocess.run(['powershell.exe', '-NoProfile', '-Command', command], capture_output=True, text=True, timeout=30)
    if proc.returncode:
        raise RuntimeError(proc.stderr)
    report = dict(created_utc=datetime.now(timezone.utc).isoformat(),
        status='matching_NetFx3_source_saved_online_install_not_yet_verified',
        package=dict(path=str(source), bytes=source.stat().st_size, sha256=actual,
                     hash_matches_Windows_ActionList=True),
        CLR2_DLL_present=Path('C:/Windows/Microsoft.NET/Framework/v2.0.50727/mscorwks.dll').is_file(),
        DISM_processes=json.loads(proc.stdout) if proc.stdout.strip() else [],
        editor_launch_verified=False, HMI_compiled=False, automatic_reboot=False,
        system_services_ACL_or_policy_changes=False, board_operations=False,
        note='Feature status is not established by this download snapshot. Recheck final DISM report and actual feature state.')
    (out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(out / 'report.json')


if __name__ == '__main__':
    main()
