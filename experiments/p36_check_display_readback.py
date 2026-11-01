"""Host-only parser/safety checks. Does not construct BoardConsole/open a UART."""
import ast
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import unittest

import p36_display_readback as target


CLOCKS = '''clock enable_cnt prepare_cnt rate accuracy phase
 fclk0 1 1 100000000 0 0
    43c10000.clk_wiz_mul 1 1 4950000000 0 0
       43c10000.clk_wiz_mul_div 1 1 990000000 0 0
          clk_out1 1 1 33000000 0 0
 fclk1 1 1 200000000 0 0
'''
BINDING = dict(device='/sys/bus/platform/devices/43c10000.clk_wiz',
               driver='../../../bus/platform/drivers/clk-wizard',
               compatible=['xlnx,clocking-wizard'],
               resources=[[0x43C10000, 0x43C1FFFF, 0x200]])
PWM = '''platform/amba:ttc_pwm@0, 3 PWM devices
 pwm-0 ((null)): period: 0 ns duty: 0 ns polarity: normal
 pwm-1 ((null)): period: 0 ns duty: 0 ns polarity: normal
 pwm-2 (backlight): requested enabled period: 50000 ns duty: 50000 ns polarity: normal
'''


class Checks(unittest.TestCase):
    def test_source_offsets_and_identity(self):
        source = target.source_contract()
        self.assertEqual((source['status_offset'], source['feedback_offset'], source['output0_offset']), (4, 0x200, 0x208))

    def test_source_real_saved_clock_summary(self):
        path = target.ROOT / 'results/p35-firmware-readback-20261020T155937Z/report.json'
        report = json.loads(path.read_text('utf-8'))
        raw = next(stage['output'] for stage in report['stages']
                   if stage.get('command') == 'cat /sys/kernel/debug/clk/clk_summary')
        clocks = target.parse_clocks(raw)
        self.assertGreater(clocks['fclk0']['rate_hz'], 99000000)

    def test_fractional_decode_33MHz(self):
        registers = dict(status=1, feedback=5 | (49 << 8) | (500 << 16), output0=30)
        decoded = target.decode_wizard(registers, 100000000, 33000000)
        self.assertTrue(decoded['locked'])
        self.assertEqual(decoded['predicted_output_hz'], 33000000)
        self.assertTrue(decoded['software_matches_prediction_within_1kHz'])

    def test_unlocked_is_not_accepted_as_locked(self):
        registers = dict(status=0, feedback=5 | (49 << 8) | (500 << 16), output0=30)
        self.assertFalse(target.decode_wizard(registers, 100000000)['locked'])

    def test_zero_and_out_of_range_dividers(self):
        registers = dict(status=1, feedback=(49 << 8), output0=30)
        self.assertFalse(target.decode_wizard(registers, 100000000)['valid_dividers'])
        registers['feedback'] = 5 | (49 << 8) | (1001 << 16)
        self.assertFalse(target.decode_wizard(registers, 100000000)['valid_dividers'])

    def test_register_gate_positive_and_negative_cases(self):
        clocks = target.parse_clocks(CLOCKS)
        self.assertTrue(target.wizard_gate(BINDING, clocks, 'operating')['allowed'])
        for property_name, bad in [('driver', ''), ('compatible', []), ('resources', [[0x43C00000, 0x43C0FFFF, 0x200]])]:
            binding = copy.deepcopy(BINDING)
            binding[property_name] = bad
            self.assertFalse(target.wizard_gate(binding, clocks, 'operating')['allowed'])
        clocks['clk_out1']['enable_count'] = 0
        self.assertFalse(target.wizard_gate(BINDING, clocks, 'operating')['allowed'])
        self.assertFalse(target.wizard_gate(BINDING, clocks, 'unknown')['allowed'])

    def test_duplicate_and_unknown_clock_formats_rejected(self):
        with self.assertRaises(ValueError):
            target.parse_clocks(CLOCKS + ' fclk0 1 1 100000000 0 0\n')
        with self.assertRaises(ValueError):
            target.parse_clocks('clock rate\nfclk0 100000000\n')

    def test_double_buffer_is_valid_storage_not_visible_geometry(self):
        parsed = target.framebuffer_storage('800,960', '32', '3200')
        self.assertTrue(parsed['accommodates_800x480_32bpp'])
        self.assertFalse(parsed['virtual_dimensions_prove_visible_dimensions'])
        self.assertFalse(target.framebuffer_storage('800,480', '32', '3199')['accommodates_800x480_32bpp'])

    def test_pwm2_does_not_confuse_other_provider_or_timer_channels(self):
        self.assertTrue(target.pwm_state(PWM)['PWM2_requested_enabled_50us_nonzero_duty'])
        self.assertTrue(target.pwm_state(PWM)['PWM0_PWM1_not_requested'])
        self.assertFalse(target.pwm_state(PWM.replace('pwm-0 ((null)):', 'pwm-0 (bad): requested'))['PWM0_PWM1_not_requested'])
        self.assertFalse(target.pwm_state(PWM.replace('ttc_pwm', 'unrelated_pwm'))['known'])

    def test_framing_preserves_read_error(self):
        raw = '# echo __B36__;cat "$p";r=$?;echo __E36__$r\r\n__B36__\r\ncat: missing\r\n__E36__1\r\n__P32_12345678__:0\r\n'
        self.assertEqual(target.parse_frame(raw), ('cat: missing', 1))

    def test_literal_capture_commands_fit_UART_limit(self):
        tree = ast.parse(Path(target.__file__).read_text('utf-8'))
        bodies = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'capture' and len(node.args) >= 2:
                if isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str):
                    bodies.append(node.args[1].value)
        bodies += ['cat "$p"', "printf '%s\\n' $p/*", 'readlink "$p/driver"',
                   'cat "$p/resource"', 'od -An -tx1 "$p/compatible"']
        bodies += [f'devmem 0x{address:08x} 32' for address in target.REGISTERS.values()]
        self.assertGreater(len(bodies), 10)
        for body in bodies:
            self.assertLessEqual(len(target.frame_command(body)), 72)
            self.assertNotIn(' > ', body)
            if body.startswith('devmem '):
                self.assertEqual(len(body.split()), 3)  # No write-value argument.


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Checks)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    out = target.ROOT / 'results' / datetime.now(timezone.utc).strftime('p36-display-offline-check-%Y%m%dT%H%M%SZ')
    out.mkdir(exist_ok=False)
    (out / 'report.json').write_text(json.dumps(dict(
        schema='rfsig.p36_display_offline_check.v1', board_access=False,
        serial_opened=False, tests_run=result.testsRun,
        failures=len(result.failures), errors=len(result.errors),
        status='passed_host_only' if result.wasSuccessful() else 'failed'), indent=2) + '\n', encoding='utf-8')
    print(out)
    raise SystemExit(0 if result.wasSuccessful() else 1)
