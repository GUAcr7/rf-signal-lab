"""Read selected vendor kernel sources from the untouched supplied archive."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = Path('D:/AD9361/AD9361/软件资料/Linux/Kernel/src/linux-xlnx-ad-fmcomms3-ebz.tar.gz')
SELECTED = ('drivers/iio/adc/cf_axi_adc_core.c', 'drivers/dma/dma-axi-dmac.c',
            'drivers/of/overlay.c', 'drivers/of/configfs.c',
            'include/config/kernel.release', 'include/generated/utsrelease.h',
            '.scmversion', '.git/HEAD', '.git/packed-refs', '.git/refs/heads/master')


def main():
    out = ROOT / 'results' / datetime.now(timezone.utc).strftime('p31-vendor-kernel-%Y%m%dT%H%M%SZ')
    out.mkdir(exist_ok=False)
    report = dict(status='reading', source=str(ARCHIVE), files=[],
        archive_modified=False, exact_running_build_match_proven=False)
    with ARCHIVE.open('rb') as stream:
        report['archive_sha256'] = hashlib.file_digest(stream, 'sha256').hexdigest()
    with tarfile.open(ARCHIVE, 'r|gz') as archive:
        for member in archive:
            # This supplied tar has root-level drivers/, not an outer folder.
            # Use an explicit allowlist and never extract archive paths.
            relative = member.name.removeprefix('./')
            if not member.isfile() or not (relative in SELECTED or relative == 'Makefile'):
                continue
            if member.size > 4 * 1024 * 1024:
                raise RuntimeError('unexpected selected file size')
            data = archive.extractfile(member).read()
            name = relative.replace('/', '__') + '.txt'
            (out / name).write_bytes(data)
            report['files'].append(dict(member=member.name, file=name, bytes=len(data),
                sha256=hashlib.sha256(data).hexdigest()))
    required = {'drivers/iio/adc/cf_axi_adc_core.c', 'drivers/dma/dma-axi-dmac.c',
                'drivers/of/overlay.c', 'Makefile'}
    found = {f['member'].removeprefix('./') for f in report['files']}
    report['missing_required'] = sorted(required - found)
    report['status'] = 'failed_missing_sources' if required - found else 'selected_sources_archived_for_review'
    (out / 'report.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(out)
    print(report['status'])
    print('\n'.join(f['member'] for f in report['files']))


if __name__ == '__main__':
    main()
