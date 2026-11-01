"""Read ClockWiz registers only after a fresh live DT/driver/clock address gate.

No UART is opened until main() is explicitly executed. No register/sysfs writes,
driver changes, mode changes or FPGA configuration. Unknown evidence means skip.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import PurePosixPath
import re
import struct

from p32_session import BoardConsole, ROOT
from p36_display_readback import (
    AuditPort, Reader, REGISTERS, RF_NAMES, decode_wizard, parse_clocks,
    source_contract, wizard_gate,
)

DT_ROOT = '/sys/firmware/devicetree/base'


def binary_read(reader, key, node, prop):
    """od preserves an empty DT property versus an unavailable property."""
    if prop not in {'reg', 'ranges', '#address-cells', '#size-cells', 'compatible'}:
        raise ValueError('unexpected DT property')
    reader.path(node)
    item = reader.capture(key, 'od -An -tx1 "$p/' + prop + '"')
    fields = item['text'].split()
    if not item['available'] or not all(re.fullmatch(r'[0-9a-fA-F]{2}', v) for v in fields):
        return None
    return bytes.fromhex(' '.join(fields))


def translate_reg(reg, bus_address, bus_size, root_address, root_size, ranges):
    """Accept only explicit 32-bit parent/root contracts, with unique mapping.

    This limited verifier supports a device directly below /amba below DT root.
    It does not infer missing cells, treat absent ranges as identity, or guess
    translation for any other bus topology.
    """
    values = {'bus_address_cells': bus_address, 'bus_size_cells': bus_size,
              'root_address_cells': root_address, 'root_size_cells': root_size}
    reasons = []
    for label, raw in values.items():
        if raw != b'\x00\x00\x00\x01':
            reasons.append(label + ' not explicitly one 32-bit cell')
    if reg is None or len(reg) != 8:
        reasons.append('reg not exactly one explicit 32-bit address/size tuple')
    if ranges is None:
        reasons.append('ranges unavailable; absent is not treated as identity')
    elif len(ranges) % 12:
        reasons.append('ranges does not contain complete 32-bit child/parent/size tuples')
    if reasons:
        return dict(allowed=False, reasons=reasons)
    address, size = struct.unpack('>II', reg)
    if not size or address + size > 0x100000000:
        return dict(allowed=False, reasons=['zero/overflowing reg range'])
    decoded_ranges = [struct.unpack('>III', ranges[n:n + 12]) for n in range(0, len(ranges), 12)]
    if not decoded_ranges:
        translated, translation = address, 'explicit_empty_ranges_identity'
    else:
        hits = []
        for child, parent, span in decoded_ranges:
            if not span or child + span > 0x100000000 or parent + span > 0x100000000:
                return dict(allowed=False, reasons=['zero/overflowing ranges tuple'])
            # Any partial intersecting mapping is ambiguous for this resource.
            if child < address + size and address < child + span:
                if child <= address and address + size <= child + span:
                    hits.append(parent + address - child)
                else:
                    return dict(allowed=False, reasons=['reg crosses a ranges boundary'])
        if len(hits) != 1:
            return dict(allowed=False, reasons=['resource has zero/multiple ranges mappings'])
        translated, translation = hits[0], 'unique_explicit_ranges_mapping'
    if translated != 0x43C10000 or size != 0x10000:
        return dict(allowed=False, reasons=['translated resource differs from 0x43c10000/0x10000'],
                    bus_address=address, size=size, translated_address=translated)
    return dict(allowed=True, reasons=[], bus_address=address, size=size,
                translated_address=translated, translated_end=translated + size - 1,
                translation=translation, decoded_ranges=decoded_ranges,
                resource_proof='live DT reg + explicit parent/root cell widths and ranges')


def iomem_evidence(text, device_name, of_label=None):
    entries = []
    for line in text.splitlines():
        found = re.match(r'\s*([0-9a-fA-F]+)-([0-9a-fA-F]+)\s*:\s*(.+)$', line)
        if found:
            start, end, label = int(found[1], 16), int(found[2], 16), found[3]
            if start <= 0x43C1020B and end >= 0x43C10000:
                entries.append(dict(start=start, end=end, label=label))
    matching = [v for v in entries if v['start'] == 0x43C10000 and v['end'] >= 0x43C1020B
                and (device_name in v['label'] or 'clk-wizard' in v['label']
                     or (of_label is not None and v['label'] == of_label))]
    conflicts = [v for v in entries if v['start'] == 0x43C10000 and v not in matching]
    return dict(entries=entries, corroborates=bool(matching), contradictory_exact_base=bool(conflicts),
                limitation='Corroboration of DT translation; absence alone is not an address proof.')


def read_mapping(reader, device):
    reader.path(device)
    driver = reader.capture('ClockWiz_live_driver', 'readlink "$p/driver"')
    resolved = reader.capture('ClockWiz_live_of_node', 'readlink -f "$p/of_node"')
    node = resolved['text'] if resolved['available'] else ''
    binding = dict(device=device, driver=driver['text'] if driver['available'] else '',
                   compatible=[], resources=[], resource_origin='not_established')
    topology_ok = (node.startswith(DT_ROOT + '/amba/') and
                   PurePosixPath(node).parent.as_posix() == DT_ROOT + '/amba' and
                   PurePosixPath(node).name.endswith('@43c10000'))
    if not topology_ok:
        return binding, dict(allowed=False, reasons=['unsupported/unresolved live of_node topology'], node=node)
    raw = binary_read(reader, 'ClockWiz_DT_compatible', node, 'compatible')
    if raw is not None:
        try:
            binding['compatible'] = raw.rstrip(b'\x00').decode('ascii').split('\x00')
        except UnicodeDecodeError:
            pass
    bus = PurePosixPath(node).parent.as_posix()
    values = [binary_read(reader, 'ClockWiz_DT_reg', node, 'reg')]
    for label, path, prop in [
        ('bus_address_cells', bus, '#address-cells'), ('bus_size_cells', bus, '#size-cells'),
        ('root_address_cells', DT_ROOT, '#address-cells'), ('root_size_cells', DT_ROOT, '#size-cells'),
        ('bus_ranges', bus, 'ranges'),
    ]:
        values.append(binary_read(reader, label, path, prop))
    mapping = translate_reg(*values)
    mapping['node'] = node
    if mapping['allowed']:
        # Existing gate receives a resource proven from live DT, explicitly
        # labelled as such rather than fabricated platform resource readback.
        binding['resources'] = [[mapping['translated_address'], mapping['translated_end'], 0x200]]
        binding['resource_origin'] = 'live_DT_translation_verified'
    return binding, mapping


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-boot', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', args.expected_boot):
        parser.error('--expected-boot must be a freshly read UUID')
    source = source_contract()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out = ROOT / 'results' / ('p36-clockwiz-readback-' + stamp)
    out.mkdir(exist_ok=False)
    report = dict(schema='rfsig.p36_clockwiz_readback.v1', status='reading',
                  stages=[], reads={}, expected_boot=args.expected_boot, source=source,
                  read_only=True, register_writes=False, sysfs_writes=False,
                  physical_frequency_measured=False, physical_panel_confirmed=False,
                  serial_closed=False)

    def save():
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')

    board = None
    save()
    try:
        board = BoardConsole('COM8', report, save)
        board.port = AuditPort(board.port, out)
        board.shell()
        reader = Reader(board, report, save)
        if 'Zynq-Tronlong' not in reader.capture('identity', 'uname -a')['text']:
            raise RuntimeError('wrong board identity')
        report['boot_id'] = board.value('/proc/sys/kernel/random/boot_id')
        report['tainted_before'] = board.value('/proc/sys/kernel/tainted')
        if report['boot_id'] != args.expected_boot or report['tainted_before'] != '0':
            raise RuntimeError('unexpected boot or tainted kernel')
        names = []
        for device in reader.paths('iio_devices', '/sys/bus/iio/devices'):
            if re.search(r'/iio:device\d+$', device):
                item = reader.file(device + ':name', device + '/name')
                if item['available']:
                    names.append(item['text'])
        report['IIO_names'] = names
        if not RF_NAMES <= set(names) or len(names) != len(set(names)):
            raise RuntimeError('RF names missing/ambiguous')
        if not reader.capture('fb0_device', 'test -c /dev/fb0')['available']:
            raise RuntimeError('fb0 character device absent')
        fabric = reader.file('fabric', '/sys/class/fpga_manager/fpga0/state')['text']
        reader.file('interrupts_before', '/proc/interrupts')
        iomem = reader.file('iomem', '/proc/iomem')
        devices = reader.paths('platform_devices', '/sys/bus/platform/devices')
        candidates = [v for v in devices if PurePosixPath(v).name == '43c10000.clk_wiz']
        if len(candidates) == 1:
            binding, mapping = read_mapping(reader, candidates[0])
            report['binding'], report['DT_address_gate'] = binding, mapping
            # This kernel labels the reservation by the exact live OF path,
            # e.g. /amba/clk_wiz@43c10000, rather than the platform basename.
            of_label = mapping.get('node', '').removeprefix(DT_ROOT)
            evidence = iomem_evidence(iomem['text'], PurePosixPath(candidates[0]).name,
                                     of_label if mapping['allowed'] else None)
            report['iomem_corroboration'] = evidence
            summary = reader.file('clk_summary', '/sys/kernel/debug/clk/clk_summary')
            try:
                clocks = parse_clocks(summary['text'])
            except ValueError as exc:
                clocks = {}
                report['clock_parse_error'] = str(exc)
            report['clocks'] = clocks
            gate = wizard_gate(binding, clocks, fabric)
            if not mapping['allowed']:
                gate['allowed'] = False
                gate['reasons'] += mapping['reasons']
            if evidence['contradictory_exact_base']:
                gate['allowed'] = False
                gate['reasons'].append('/proc/iomem contains a contradictory exact-base resource')
            report['register_read_gate'] = gate
            if gate['allowed']:
                tool = reader.capture('devmem_command', 'command -v devmem')
                if tool['available'] and re.fullmatch(r'/[A-Za-z0-9_/.-]+', tool['text'].strip()):
                    registers = {}
                    for key, address in REGISTERS.items():
                        item = reader.capture('ClockWiz_' + key, f'devmem 0x{address:08x} 32')
                        if item['available'] and re.fullmatch(r'0[xX][0-9a-fA-F]{1,8}', item['text']):
                            registers[key] = int(item['text'], 16)
                    report['registers'] = registers
                    if set(registers) == set(REGISTERS):
                        report['decoded'] = decode_wizard(registers, clocks['fclk0']['rate_hz'], clocks['clk_out1']['rate_hz'])
                    else:
                        report['skip'] = 'one or more MMIO reads failed/unrecognized; raw evidence retained'
                else:
                    report['skip'] = 'devmem unavailable or path unrecognized; no MMIO read attempted'
            else:
                report['skip'] = 'DT/driver/clock gate not established; no MMIO read attempted'
        else:
            report['skip'] = 'unique expected live ClockWiz device not established; no MMIO read attempted'
        reader.file('interrupts_after', '/proc/interrupts')
        reader.capture('kernel_tail', 'dmesg | tail -n 100', timeout=20)
        report['boot_id_after'] = board.value('/proc/sys/kernel/random/boot_id')
        report['tainted_after'] = board.value('/proc/sys/kernel/tainted')
        if report['boot_id_after'] != args.expected_boot or report['tainted_after'] != '0':
            raise RuntimeError('final boot/taint state changed')
        report['optional_reads_unavailable'] = [k for k, v in report['reads'].items() if not v['available']]
        report['status'] = 'read_only_evidence_collected'
    except Exception as exc:
        report.update(status='stopped', error=repr(exc))
    finally:
        if board:
            board.close()
        report['serial_closed'] = True
        save()
        print(out)
        print(json.dumps({k: report.get(k) for k in ['status', 'register_read_gate', 'skip', 'decoded']}, indent=2))
    return 0 if report['status'] == 'read_only_evidence_collected' else 1


if __name__ == '__main__':
    raise SystemExit(main())
