"""Read the locally saved T1 HMI seed using a pinned MIT file parser; no UI/IO."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
TOOLS = Path('E:/FPGA_Tools/TJC-Projects/hmi-file-tools-20261025')
SEED = Path('E:/FPGA_Tools/TJC-Projects/P66-20261025/p201-source.HMI')


def main():
    commit = subprocess.check_output(['git', '-C', str(TOOLS), 'rev-parse', 'HEAD'], text=True).strip()
    if commit != '7aa9fb690a5de024b6caaabd44d0a1db1d649001':
        raise ValueError('File tool revision changed')
    sys.path.insert(0, str(TOOLS))
    from usarthmi.hmi_inspect import inspect_hmi
    out = ROOT / 'results' / datetime.now(timezone.utc).strftime('p66-seed-%Y%m%dT%H%M%SZ')
    out.mkdir(exist_ok=False)
    shutil.copyfile(SEED, out / 'official-T1-seed.HMI')
    shutil.copyfile(TOOLS / 'LICENSE', out / 'file-tool-LICENSE.txt')
    result = inspect_hmi(out / 'official-T1-seed.HMI').to_dict()
    (out / 'inspection.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    report = dict(status='read_only_official_T1_seed_inspection', source=str(SEED),
        seed_sha256=hashlib.sha256(SEED.read_bytes()).hexdigest(),
        file_tool_repository='https://github.com/YXerer668/tjc-usart-hmi-toolchain',
        file_tool_commit=commit, board_operations=False, HMI_compiled=False,
        TFT_downloaded=False, official_editor_reopen_required_after_file_generation=True)
    (out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(out)
    print('Entries:', [item['name'] for item in result['entries']])
    for page in result['pa_pages']:
        print('Page:', page['entry_name'], page['parse_status'], page['parse_error'])
        for block in page['blocks']:
            print(json.dumps(block, ensure_ascii=False))


if __name__ == '__main__':
    main()
