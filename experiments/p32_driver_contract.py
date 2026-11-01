"""Offline-only archive of exact vendor source evidence; no hardware access."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = Path('D:/AD9361/AD9361/软件资料/Linux/Kernel/src/linux-xlnx-ad-fmcomms3-ebz.tar.gz')
SELECTED = {
    'drivers/dma/dma-axi-dmac.c', 'drivers/dma/xilinx/xilinx_dma.c',
    'drivers/dma/xilinx/xilinx_vdma.c', 'drivers/clocksource/timer-cadence-ttc.c',
    'drivers/pwm/pwm-xilinx-ttc.c', 'drivers/pwm/pwm-zynq.c', 'drivers/pwm/pwm-cadence.c',
    'drivers/pwm/core.c', 'include/linux/clk.h',
    'drivers/pwm/Kconfig', 'drivers/pwm/Makefile',
    'Documentation/devicetree/bindings/dma/xilinx/xilinx_vdma.txt',
    'Documentation/devicetree/bindings/dma/adi,axi-dmac.txt',
    'drivers/clk/clk.c', 'drivers/clk/clkdev.c', 'drivers/of/base.c',
    'drivers/of/address.c', 'drivers/gpu/drm/xilinx/xilinx_drm_drv.c',
    'drivers/gpu/drm/xilinx/xilinx_drm_plane.c',
    '.config', 'arch/arm/configs/zynq_xcomm_adv7511_defconfig',
}


def main():
    out = ROOT / 'results' / datetime.now(timezone.utc).strftime('p32-driver-contract-%Y%m%dT%H%M%SZ')
    out.mkdir(exist_ok=False)
    files, matches = [], []
    with ARCHIVE.open('rb') as stream:
        archive_sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    with tarfile.open(ARCHIVE, 'r|gz') as archive:
        for member in archive:
            rel = member.name.removeprefix('./')
            if not member.isfile():
                continue
            interesting = ('ttc' in rel.lower() or 'vdma' in rel.lower()) and (
                rel.startswith('drivers/') or rel.startswith('Documentation/devicetree/'))
            if interesting:
                matches.append(rel)
            if rel not in SELECTED and not interesting:
                continue
            if member.size > 4 * 1024 * 1024:
                raise RuntimeError('unexpected source file size: ' + rel)
            data = archive.extractfile(member).read()
            name = rel.replace('/', '__') + '.txt'
            (out / name).write_bytes(data)
            files.append(dict(member=rel, file=name, bytes=len(data), sha256=hashlib.sha256(data).hexdigest()))
    report = dict(status='sources_archived_review_pending', created_utc=datetime.now(timezone.utc).isoformat(),
        archive=str(ARCHIVE), archive_sha256=archive_sha, files=files, matched_names=matches,
        selected_not_present=sorted(SELECTED - {f['member'] for f in files}),
        board_operations=False, exact_running_build_match_proven=False)
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(out)
    print(json.dumps(dict(files=len(files), matches=matches, absent=report['selected_not_present']), indent=2))


if __name__ == '__main__':
    main()
