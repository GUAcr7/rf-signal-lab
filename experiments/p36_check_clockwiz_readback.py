"""Host-only DT address, mapping, and command-length checks; no UART."""
import ast
from datetime import datetime, timezone
import json
from pathlib import Path
import struct
import unittest

import p36_clockwiz_readback as target
from p36_display_readback import frame_command

ONE = struct.pack('>I', 1)
REG = struct.pack('>II', 0x43C10000, 0x10000)


def gate(reg=REG, ranges=b'', cells=None):
    return target.translate_reg(reg, *(cells or [ONE] * 4), ranges)


class Checks(unittest.TestCase):
    def test_explicit_identity_maps_exact_address(self):
        result = gate()
        self.assertTrue(result['allowed'])
        self.assertEqual(result['translated_address'], 0x43C10000)
        self.assertEqual(result['translation'], 'explicit_empty_ranges_identity')

    def test_absent_ranges_not_identity(self):
        self.assertFalse(gate(ranges=None)['allowed'])

    def test_missing_non32bit_cells_rejected(self):
        for index in range(4):
            for value in [None, b'', struct.pack('>I', 2), b'\x01']:
                cells = [ONE] * 4
                cells[index] = value
                self.assertFalse(gate(cells=cells)['allowed'])

    def test_unique_explicit_range_and_ambiguous_range(self):
        valid = struct.pack('>III', 0x40000000, 0x40000000, 0x10000000)
        self.assertTrue(gate(ranges=valid)['allowed'])
        self.assertFalse(gate(ranges=valid + valid)['allowed'])
        self.assertFalse(gate(ranges=valid[:-1])['allowed'])
        self.assertFalse(gate(ranges=struct.pack('>III', 0x43C18000, 0x43C18000, 0x10000))['allowed'])

    def test_wrong_reg_zero_size_and_overflow_rejected(self):
        for reg in [None, b'', REG + REG, struct.pack('>II', 0x43C00000, 0x10000),
                    struct.pack('>II', 0x43C10000, 0), struct.pack('>II', 0xFFFFF000, 0x10000)]:
            self.assertFalse(gate(reg=reg)['allowed'])

    def test_wrong_translation_and_no_mapping_rejected(self):
        self.assertFalse(gate(ranges=struct.pack('>III', 0x40000000, 0x30000000, 0x10000000))['allowed'])
        self.assertFalse(gate(ranges=struct.pack('>III', 0x40000000, 0x40000000, 0x10000))['allowed'])

    def test_iomem_matching_and_conflict(self):
        proof = target.iomem_evidence(' 43c10000-43c1ffff : 43c10000.clk_wiz\n', '43c10000.clk_wiz')
        self.assertTrue(proof['corroborates'])
        self.assertFalse(proof['contradictory_exact_base'])
        bad = target.iomem_evidence('43c10000-43c1ffff : another-device\n', '43c10000.clk_wiz')
        self.assertTrue(bad['contradictory_exact_base'])
        self.assertFalse(bad['corroborates'])

    def test_commands_fit_and_devmem_has_no_write_value(self):
        tree = ast.parse(Path(target.__file__).read_text('utf-8'))
        bodies = [node.args[1].value for node in ast.walk(tree)
                  if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and
                  node.func.attr == 'capture' and len(node.args) >= 2 and
                  isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str)]
        bodies += ['od -An -tx1 "$p/' + prop + '"' for prop in ['reg', 'ranges', '#address-cells', '#size-cells', 'compatible']]
        bodies += [f'devmem 0x{address:08x} 32' for address in target.REGISTERS.values()]
        for body in bodies:
            self.assertLessEqual(len(frame_command(body)), 72)
            if body.startswith('devmem '):
                self.assertEqual(len(body.split()), 3)
        self.assertGreater(len(bodies), 10)


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Checks))
    out = target.ROOT / 'results' / datetime.now(timezone.utc).strftime('p36-clockwiz-offline-check-%Y%m%dT%H%M%SZ')
    out.mkdir(exist_ok=False)
    (out / 'report.json').write_text(json.dumps(dict(
        schema='rfsig.p36_clockwiz_offline_check.v1', board_access=False, serial_opened=False,
        tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors),
        status='passed_host_only' if result.wasSuccessful() else 'failed'), indent=2) + '\n', encoding='utf-8')
    print(out)
    raise SystemExit(0 if result.wasSuccessful() else 1)
