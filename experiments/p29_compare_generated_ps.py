"""Compare selected live SLCR readbacks with PS-init code from both generated IPs."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]


def main():
    readback_path = sorted((ROOT/'results').glob('p29-ps-readback-*/report.json'))[-1]
    readback = json.loads(readback_path.read_text('utf-8'))
    if readback['status'] != 'selected_registers_read_only_archived':
        raise RuntimeError('readback not accepted')
    active = json.loads((ROOT/'results/p29-active-build.json').read_text('utf-8'))
    roots = {'display': Path(active['display_short_project']).parent, 'rf': Path(active['work'])/'rf'}
    out = ROOT/'results'/datetime.now(timezone.utc).strftime('p29-ps-generated-comparison-%Y%m%dT%H%M%SZ')
    out.mkdir(exist_ok=False)
    report = dict(status='selected_register_comparison_only', readback=str(readback_path),
                  board_operations=False, full_PS_configuration_verified=False, candidates={})
    for name, root in roots.items():
        candidates = list(root.rglob('ps7_init.c'))
        if len(candidates) != 1:
            raise RuntimeError('ambiguous PS init code')
        path = candidates[0]
        text = path.read_text('utf-8')
        writes = {}
        for address, mask, value in re.findall(r'EMIT_MASKWRITE\(\s*(0[Xx][0-9A-Fa-f]+),\s*(0[Xx][0-9A-Fa-f]+)U?\s*,\s*(0[Xx][0-9A-Fa-f]+)U?\s*\)', text):
            writes.setdefault(int(address,16), set()).add((int(mask,16), int(value,16)))
        rows = []
        for register in readback['registers']:
            address, actual = int(register['address'],16), int(register['value'],16)
            values = sorted(writes.get(address, []))
            if not values:
                rows.append(dict(label=register['label'], readback=register['value'],
                                 all_candidate_masks_match=None, masks=[],
                                 note='Generated source does not program this address; no comparison claim.'))
                continue
            matches = all((actual & m)==(v & m) for m,v in values)
            rows.append(dict(label=register['label'], readback=register['value'], all_candidate_masks_match=matches,
                             masks=[dict(mask=f'0x{m:08X}', value=f'0x{v:08X}') for m,v in values]))
        shutil.copy2(path, out/(name+'-generated-ps7_init.c'))
        report['candidates'][name] = dict(source=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            registers=rows, matched=sum(r['all_candidate_masks_match'] is True for r in rows),
            comparable=sum(bool(r['masks']) for r in rows), total=len(rows))
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(out)
    for name, candidate in report['candidates'].items():
        print(name, candidate['matched'], '/', candidate['comparable'], '(readbacks',candidate['total'],')')
        for row in candidate['registers']:
            print(row['label'], row['readback'], row['all_candidate_masks_match'])


if __name__ == '__main__':
    main()
