"""Compare supplied boot artifacts and locate PS init sources without modifying board/files."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    out = ROOT / 'results' / datetime.now(timezone.utc).strftime('p29-ps-boot-baseline-%Y%m%dT%H%M%SZ')
    out.mkdir(exist_ok=False)
    packages = {'display': Path('D:/xilinx/xilinx/4-软件资料/Linux/FSBL'),
                'rf': Path('D:/AD9361/AD9361/软件资料/Linux/FSBL')}
    files = {}
    sources = {}
    ps_init = {}
    for name, root in packages.items():
        files[name] = {}
        for filename in ['fsbl.elf', 'BOOT.BIN']:
            path = root / 'image/embeddedsw-gdea7f98-v1.1' / filename
            files[name][filename] = dict(path=str(path), bytes=path.stat().st_size,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        archive = root / 'src/embeddedsw-gdea7f98-v1.1.tar.gz'
        with tarfile.open(archive, 'r:gz') as tar:
            sources[name] = [m.name for m in tar.getmembers() if m.isfile() and
                             ('ps7_init' in m.name.lower() or 'tlz7' in m.name.lower())]
            member = 'lib/sw_apps/zynq_fsbl/src/ps7_init.c'
            raw = tar.extractfile(member).read()
            target = out / (name + '-ps7_init.c')
            target.write_bytes(raw)
            ps_init[name] = dict(archive_member=member, file=target.name,
                                 sha256=hashlib.sha256(raw).hexdigest())
    matches = {filename: files['rf'][filename]['sha256'] == files['display'][filename]['sha256']
               for filename in ['fsbl.elf', 'BOOT.BIN']}
    (out / 'report.json').write_text(json.dumps(dict(status='read_only_comparison', files=files,
        matching_artifacts=matches, ps_init_sources=ps_init,
        ps_init_source_candidates=sources, board_operations=False,
        running_boot_artifact_identified=False,
        note='Package byte identity does not identify the active boot partition. Do not regenerate FSBL from the RF project PS settings.'), indent=2) + '\n', encoding='utf-8')
    print(out)
    print('matching artifacts', matches)
    print('PS init source candidates', {k: len(v) for k,v in sources.items()})
    for name in sources['display'][:8]:
        print(name)


if __name__ == '__main__':
    main()
