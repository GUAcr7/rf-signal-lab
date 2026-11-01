"""Read original DT blobs and tool availability; never apply an overlay."""
from datetime import datetime, timezone
import hashlib
import json
import re
from p26_retrieve_chunks import ChunkConsole,decode_payload,ROOT


def main():
    state=json.loads((ROOT/'TX-SOURCE-STATUS.json').read_text('utf-8'))['p30_integration']
    out=ROOT/'results'/('p31-board-contract-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    out.mkdir(exist_ok=False)
    report=dict(status='running',stages=[],read_only=True,RF_writes=False,overlay_applied=False,files=[])
    def save():(out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    save();board=None
    try:
        board=ChunkConsole('COM8',report,save)
        if 'Zynq-Tronlong' not in board.command('uname -a'):raise RuntimeError('wrong board')
        if state['rx_boot_id'] not in board.command('cat /proc/sys/kernel/random/boot_id'):raise RuntimeError('receiver rebooted')
        for command in ['cat /etc/board-mode','/etc/rcS.d/S99board --check-rf','command -v dtc || true','command -v fdtoverlay || true',
                'cat /proc/iomem','cat /sys/kernel/debug/clk/clk_summary',
                'ls /sys/kernel/config/device-tree/overlays']:
            board.command(command)
        for source,name in [('/lib/firmware/pl.dtbo','factory-rf.dtbo'),('/lib/firmware/d480p.dtbo','factory-display.dtbo'),('/sys/firmware/fdt','boot-base.dtb')]:
            board.command('p='+source)
            length=board.command('n=$(wc -c <$p); echo __SIZE__${n}__END__')
            sizes=re.findall(r'^__SIZE__(\d+)__END__\r?$',length,re.M)
            if len(sizes)!=1:raise RuntimeError('size ambiguous')
            size=int(sizes[0])
            if not 40<=size<=262144:raise RuntimeError('unexpected FDT size')
            digest=re.search(r'^([0-9a-f]{64})\s',board.command('sha256sum $p'),re.M)[1]
            data=decode_payload(board.command('base64 $p',timeout=30),size)
            if hashlib.sha256(data).hexdigest()!=digest:raise RuntimeError('FDT hash mismatch')
            (out/name).write_bytes(data)
            report['files'].append(dict(source=source,file=name,bytes=size,sha256=digest));save()
        report['boot_id']=state['rx_boot_id'];report['status']='original_blobs_and_runtime_contract_archived_read_only'
    except Exception as error:report.update(status='failed',error=repr(error))
    finally:
        if board:board.close()
        save()
    print(out);print(report['status'])
    if 'error' in report:print(report['error'])
    return 0 if report['status'].endswith('_read_only') else 1


if __name__=='__main__':raise SystemExit(main())
