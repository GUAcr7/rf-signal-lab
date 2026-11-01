"""Read a bounded set of documented PS-init SLCR words; never write a register."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from p22_acquire_comparison import Console, ROOT


def main():
    ps_sources = sorted((ROOT / 'results').glob('p29-ps-boot-baseline-*/display-ps7_init.c'))[-1]
    text = ps_sources.read_text('utf-8')
    labels = {'MIO0': 0xF8000700, 'MIO8_fan': 0xF8000720, 'MIO12': 0xF8000730,
              'MIO13': 0xF8000734, 'MIO48': 0xF80007C0, 'MIO49': 0xF80007C4,
              'FPGA0_CLK_CTRL': 0xF8000170, 'FPGA1_CLK_CTRL': 0xF8000180,
              'FPGA2_CLK_CTRL': 0xF8000190, 'FPGA3_CLK_CTRL': 0xF80001A0}
    writes = {}
    for address, mask, value in re.findall(r'EMIT_MASKWRITE\(\s*(0X[0-9A-Fa-f]+),\s*(0x[0-9A-Fa-f]+)U?\s*,\s*(0x[0-9A-Fa-f]+)U?\s*\)', text):
        writes.setdefault(int(address, 16), set()).add((int(mask,16), int(value,16)))
    if not set(labels.values()) <= set(writes):
        raise RuntimeError('selected address absent from retained PS init source')
    out = ROOT / 'results' / datetime.now(timezone.utc).strftime('p29-ps-readback-%Y%m%dT%H%M%SZ')
    out.mkdir(exist_ok=False)
    report = dict(status='running', stages=[], read_only=True, register_writes=False,
                  source_candidate=str(ps_sources), candidate_is_running_boot_source_proven=False, registers=[])
    def save():
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    save()
    console = None
    try:
        console = Console('COM8', report, save)
        if 'Zynq-Tronlong' not in console.command('uname -a'):
            raise RuntimeError('wrong board')
        console.command('cat /proc/sys/kernel/random/boot_id')
        console.command('command -v devmem')
        for label, address in labels.items():
            # Only address and width arguments. A third value argument would
            # write; this experiment deliberately never constructs one.
            output = console.command(f'devmem 0x{address:08X} 32')
            match = re.search(r'^0x([0-9A-Fa-f]{8})\r?$', output, re.M)
            if match is None:
                raise RuntimeError('register value not found')
            actual = int(match[1], 16)
            candidates = [dict(mask=f'0x{m:08X}', value=f'0x{v:08X}', matches=(actual & m)==(v & m)) for m,v in sorted(writes[address])]
            report['registers'].append(dict(label=label, address=f'0x{address:08X}', value=f'0x{actual:08X}',
                                            source_candidate_masks=candidates))
            save()
        console.command('/etc/rcS.d/S99board --check-rf')
        report['status'] = 'selected_registers_read_only_archived'
    except Exception as error:
        report.update(status='failed_or_unavailable', error=repr(error))
        raise
    finally:
        if console:
            console.close()
        save()
        print(out)


if __name__ == '__main__':
    main()
