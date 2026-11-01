"""Read staged reference designs; identify merge conflicts without modifying them."""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def pin_assignments(path):
    result = {}
    for raw in path.read_text('utf-8-sig').splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        pin = re.search(r'\bPACKAGE_PIN\s+(\w+)', line)
        port = re.search(r'\[get_ports\s+(\{[^}]+\}|[^\s\]]+)\]', line)
        if pin:
            if port is None:
                raise ValueError('unparsed pin assignment: ' + line)
            result.setdefault(pin[1], []).append(port[1].strip('{}'))
    return result


def main():
    work = Path(json.loads((ROOT / 'results/p29-active-build.json').read_text('utf-8'))['work'])
    # v2 is the completed structurally validated upgrade, with raw before/after
    # snapshots. v3 was interrupted by a tool file read error before upgrade.
    rf = work / 'rf/runs/ad-fmcomms3-ebz-xc7z100.srcs/sources_1/bd/system/system.bd'
    display = work / 'display-v2/axi_video_display.srcs/sources_1/bd/axi_video_display/axi_video_display.bd'
    designs = {name: json.loads(path.read_text('utf-8'))['design'] for name, path in [('rf', rf), ('display', display)]}
    ps = {}
    for name, design in designs.items():
        candidates = {n: c for n, c in design['components'].items() if 'processing_system7' in c.get('vlnv', '')}
        if len(candidates) != 1:
            raise ValueError(f'{name} must have exactly one PS7, got {list(candidates)}')
        ps[name] = next(iter(candidates.values()))['parameters']
    def value(parameter):
        raw = parameter['value']
        try:
            return Decimal(raw)
        except InvalidOperation:
            return raw
    deltas = []
    # Sparse BD JSON omits defaults; an absent entry is not proof of a mismatch.
    for key in sorted(set(ps['rf']) & set(ps['display'])):
        a, b = ps['rf'][key], ps['display'][key]
        if value(a) != value(b):
            deltas.append(dict(parameter=key, rf=a, display=b))
    xdc = dict(rf=work / 'rf/src/constraints/ad9361_z7xh.xdc',
               display=work / 'display-v2/axi_video_display.srcs/constrs_1/imports/constraints/axi_video_display_tlz7xh.xdc')
    pins = {name: pin_assignments(path) for name, path in xdc.items()}
    collisions = [dict(package_pin=pin, rf=pins['rf'][pin], display=pins['display'][pin])
                  for pin in sorted(set(pins['rf']) & set(pins['display']))]
    record = dict(created_utc=datetime.now(timezone.utc).isoformat(), status='planning_only_not_integrated',
                  sources={name: dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest()) for name, path in [('rf', rf), ('display', display)]},
                  design_keys={name: sorted(d) for name, d in designs.items()},
                  ps7_parameter_deltas=deltas, package_pin_collisions=collisions,
                  ps7_explicit_in_one_design_only={name: sorted(set(ps[name])-set(ps[other])) for name, other in [('rf','display'),('display','rf')]},
                  explicit_pin_counts={name: len(d) for name, d in pins.items()},
                  addressing={name: d.get('addressing', {}) for name, d in designs.items()},
                  clock_irq_ps_nets={name: {n: x for n, x in d['nets'].items()
                    if any(token in json.dumps(x) for token in ['FCLK_CLK', 'FCLK_RESET', 'IRQ_F2P', 'In0', 'In1', 'In2', 'In12', 'In13', 'GPIO_', 'SPI0_'])}
                    for name, d in designs.items()},
                  note='Static comparison only. Shared PS7, pin banks/voltage, address map, IRQ, DDR bandwidth and clocks require explicit merge validation.',
                  board_operations=False)
    out = ROOT / 'results' / datetime.now(timezone.utc).strftime('p29-integration-audit-%Y%m%dT%H%M%SZ')
    out.mkdir(exist_ok=False)
    (out / 'report.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    print(out)
    print('PS7 deltas', len(deltas), 'explicit pin collisions', len(collisions), 'pin counts', record['explicit_pin_counts'])
    print('design keys', record['design_keys'])
    for item in deltas:
        if any(word in item['parameter'] for word in ['FPGA', 'ENET0_PERIPHERAL', 'UART1_UART1_IO', 'GPIO_EMIO', 'DDR_PARTNO']):
            print(item['parameter'], item['rf']['value'], item['display']['value'])
    for name, data in record['addressing'].items():
        print('addressing', name, json.dumps(data)[:1400])
    for item in collisions:
        print(item)


if __name__ == '__main__':
    main()
