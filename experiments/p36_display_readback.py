"""Read a successfully probed merged display/RF boot; never configure hardware.

This script opens COM8 only when main() is explicitly executed by the operator.
It does not establish physical PCLK/backlight/panel visibility or RF continuity.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import time

from p32_session import BoardConsole, ROOT

RF_NAMES = {'ad9361-phy', 'cf-ad9361-lpc', 'cf-ad9361-dds-core-lpc'}
SOURCE = ROOT / ('results/p33-timing-review-20261020T113053Z/'
                 'source-drivers__clk__clk-xlnx-clock-wizard.c')
REGISTERS = {'status': 0x43C10004, 'feedback': 0x43C10200,
             'output0': 0x43C10208}
BEGIN, END = '__B36__', '__E36__'


def source_contract(path=SOURCE):
    """Pin the supplied source used for the read-only register interpretation."""
    data = path.read_bytes()
    source = data.decode('utf-8')
    required = [
        r'#define\s+WZRD_CLK_CFG_REG\(n\)\s+\(0x200 \+ 4 \* \(n\)\)',
        r'#define\s+WZRD_DR_STATUS_REG_OFFSET\s+0x04',
        r'#define\s+WZRD_DR_LOCK_BIT_MASK\s+0x00000001',
        r'#define\s+WZRD_CLKFBOUT_MULT_SHIFT\s+8',
        r'#define\s+WZRD_CLKFBOUT_FRAC_SHIFT\s+16',
        r'#define\s+WZRD_CLKOUT_FRAC_SHIFT\s+8',
        r'#define\s+WZRD_CLKOUT_FRAC_MASK\s+0x3ff',
        r'mult = \(\(reg \* 1000\) \+ reg_f\)',
        r'\(WZRD_CLK_CFG_REG\(2\) \+ i \* 12\)',
        r'\.name = "clk-wizard"',
    ]
    if not all(re.search(pattern, source) for pattern in required):
        raise RuntimeError('supplied ClockWiz source contract changed')
    return dict(path=str(path), sha256=hashlib.sha256(data).hexdigest(),
                status_offset=4, feedback_offset=0x200, output0_offset=0x208,
                fields='M[15:8]+Mfrac[25:16]/1000; D[7:0]; '
                       'O[7:0]+Ofrac[17:8]/1000; LOCK=status[0]',
                exact_running_kernel_binary_match=False,
                limitation='Supplied source interpretation; not a PCLK measurement.')


def parse_clocks(text):
    if not re.search(r'clock\s+enable_cnt\s+prepare_cnt\s+rate\s+accuracy\s+phase', text):
        raise ValueError('unknown clk_summary column contract')
    clocks, stack = {}, []
    pattern = r'^(\s*)(\S+)\s+(\d+)\s+(\d+)\s+(\d+)\s+\d+\s+[-\d]+\s*$'
    for line in text.splitlines():
        found = re.match(pattern, line)
        if not found:
            continue
        indent, name, enabled, prepared, rate = found.groups()
        if name in clocks:
            raise ValueError('duplicate clock name: ' + name)
        depth = len(indent.expandtabs(8))
        while stack and stack[-1][0] >= depth:
            stack.pop()
        clocks[name] = dict(enable_count=int(enabled), prepare_count=int(prepared),
                            rate_hz=int(rate), parents=[v[1] for v in stack])
        stack.append((depth, name))
    return clocks


def decode_wizard(registers, input_hz, software_hz=None):
    feedback, output = registers['feedback'], registers['output0']
    m_i, m_f = (feedback >> 8) & 0xff, (feedback >> 16) & 0x3ff
    d, o_i, o_f = feedback & 0xff, output & 0xff, (output >> 8) & 0x3ff
    result = dict(locked=bool(registers['status'] & 1), M_integer=m_i,
                  M_fraction_thousandths=m_f, D=d, O_integer=o_i,
                  O_fraction_thousandths=o_f, input_software_rate_hz=input_hz,
                  feedback_fraction_enable_bit=bool(feedback & (1 << 26)),
                  output_fraction_enable_bit=bool(output & (1 << 18)),
                  fractional_flag_semantics='Recorded; supplied recalc code uses fraction fields directly.')
    if not d or not o_i or not m_i or input_hz <= 0 or m_f > 999 or o_f > 999:
        result.update(valid_dividers=False, reason='zero/invalid divider or rate; no prediction')
        return result
    rate = input_hz * (m_i + m_f / 1000) / d / (o_i + o_f / 1000)
    result.update(valid_dividers=True, predicted_output_hz=rate,
                  predicted_33MHz_within_1kHz=abs(rate - 33000000) <= 1000,
                  physical_frequency_measured=False)
    if software_hz is not None:
        result['software_output_rate_hz'] = software_hz
        result['software_matches_prediction_within_1kHz'] = abs(software_hz - rate) <= 1000
    return result


def framebuffer_storage(virtual_size, bpp, stride):
    """Virtual dimensions describe storage; they are not the visible mode."""
    if not re.fullmatch(r'\d+,\d+', virtual_size):
        return dict(known=False, reason='virtual_size unavailable/unrecognized')
    width, height = map(int, virtual_size.split(','))
    try:
        bits, line_bytes = int(bpp), int(stride)
    except ValueError:
        return dict(known=False, reason='bpp/stride unavailable/unrecognized')
    return dict(known=True, virtual_width=width, virtual_height=height,
                bits_per_pixel=bits, stride_bytes=line_bytes,
                accommodates_800x480_32bpp=(width >= 800 and height >= 480 and
                                          bits == 32 and line_bytes >= width * 4),
                virtual_dimensions_prove_visible_dimensions=False)


def pwm_state(text):
    """Scope PWM channels to the TTC provider, avoiding other PWM chips."""
    providers, current = [], None
    for line in text.splitlines():
        if re.search(r'\b\d+ PWM devices\b', line):
            current = dict(header=line.strip(), channels={})
            providers.append(current)
        elif current is not None:
            found = re.search(r'\bpwm-(\d+)\b', line)
            if found:
                current['channels'][found[1]] = line.strip()
    ttc = [provider for provider in providers
           if re.search(r'ttc_pwm|f8001000', provider['header'])]
    if len(ttc) != 1:
        return dict(known=False, providers=providers,
                    reason='unique TTC provider not established')
    channels = ttc[0]['channels']
    line2 = channels.get('2', '')
    return dict(known=True, provider=ttc[0],
                PWM2_requested_enabled_50us_nonzero_duty=bool(
                    re.search(r'\brequested\b', line2) and
                    re.search(r'\benabled\b', line2) and
                    re.search(r'period:\s*50000\s*ns', line2) and
                    re.search(r'duty:\s*[1-9]\d*\s*ns', line2)),
                PWM0_PWM1_not_requested=(all(str(i) in channels for i in (0, 1)) and
                    not any(re.search(r'\brequested\b', channels[str(i)]) for i in (0, 1))))


def wizard_gate(binding, clocks, fabric):
    reasons = []
    if fabric != 'operating':
        reasons.append('fabric not positively operating')
    if Path(binding.get('driver', '')).name != 'clk-wizard':
        reasons.append('expected clk-wizard driver binding not established')
    if 'xlnx,clocking-wizard' not in binding.get('compatible', []):
        reasons.append('expected compatible not established')
    resources = binding.get('resources', [])
    if not any(start == 0x43C10000 and end >= 0x43C1020B and flags & 0x200
               for start, end, flags in resources):
        reasons.append('bound device memory resource does not cover expected registers')
    name = Path(binding.get('device', '')).name
    expected = ['fclk0', 'fclk1', name + '_mul', name + '_mul_div', 'clk_out1']
    for clock in expected:
        value = clocks.get(clock)
        if not value or value['enable_count'] <= 0 or value['prepare_count'] <= 0:
            reasons.append('clock not positively enabled/prepared: ' + clock)
    if name + '_mul_div' not in clocks.get('clk_out1', {}).get('parents', []):
        reasons.append('clk_out1 is not under this device in clk_summary')
    return dict(allowed=not reasons, reasons=reasons, expected_clocks=expected)


def frame_command(body):
    command = f'echo {BEGIN};{body};r=$?;echo {END}$r'
    if len(command) > 72 or '\n' in command or '\r' in command:
        raise ValueError('framed read command exceeds UART contract')
    return command


def parse_frame(raw):
    start = re.search(r'^' + BEGIN + r'\r?$', raw, re.M)
    finish = re.search(r'^' + END + r'(\d+)\r?$', raw, re.M)
    if not start or not finish or finish.start() <= start.end():
        raise RuntimeError('read evidence has no unambiguous output frame')
    return raw[start.end():finish.start()].strip('\r\n'), int(finish[1])


class AuditPort:
    """Keep UART receive bytes and credential-redacted transmit bytes locally."""
    def __init__(self, port, out):
        self.port = port
        self.rx = (out / 'uart.rx.bin').open('ab', buffering=0)
        self.tx = (out / 'uart.tx.bin').open('ab', buffering=0)

    def __getattr__(self, name):
        return getattr(self.port, name)

    def read(self, *args):
        data = self.port.read(*args)
        self.rx.write(data)
        return data

    def write(self, data):
        self.tx.write(b'<credential redacted>\r' if data == b'analog\r' else data)
        return self.port.write(data)

    def close(self):
        try:
            self.port.close()
        finally:
            self.rx.close()
            self.tx.close()


class Reader:
    def __init__(self, board, report, save):
        self.board, self.report, self.save = board, report, save

    def capture(self, key, body, timeout=15):
        begin = time.monotonic()
        raw = self.board.command(frame_command(body), timeout=timeout)
        end = time.monotonic()
        text, rc = parse_frame(raw)
        item = dict(text=text, read_exit_code=rc, available=rc == 0,
                    host_begin=begin, host_end=end)
        self.report['reads'][key] = item
        self.save()
        return item

    def path(self, path):
        if not re.fullmatch(r'/[A-Za-z0-9_.:/@+,-]+', path):
            raise ValueError('unsafe/unexpected sysfs path: ' + path)
        # Long discovered sysfs paths are assembled without any long UART line.
        pieces = path.split('/')[1:]
        self.board.command('p=/' + pieces.pop(0))
        for piece in pieces:
            command = 'p=$p/' + piece
            if len(command) > 72:
                raise ValueError('oversized path component')
            self.board.command(command)

    def file(self, key, path):
        self.path(path)
        return self.capture(key, 'cat "$p"')

    def paths(self, key, path):
        self.path(path)
        item = self.capture(key, "printf '%s\\n' $p/*")
        return [line for line in item['text'].splitlines()
                if line.startswith(path + '/') and not line.endswith('/*')]

    def binding(self, device):
        self.path(device)
        driver = self.capture(device + ':driver', 'readlink "$p/driver"')
        resource = self.capture(device + ':resource', 'cat "$p/resource"')
        self.path(device + '/of_node')
        compatible = self.capture(device + ':compatible', 'od -An -tx1 "$p/compatible"')
        resources = []
        for line in resource['text'].splitlines():
            fields = line.split()
            if len(fields) == 3 and all(re.fullmatch(r'(?:0x)?[0-9a-fA-F]+', f) for f in fields):
                resources.append([int(f, 16) for f in fields])
        hex_fields = compatible['text'].split()
        compat = []
        if compatible['available'] and all(re.fullmatch('[0-9a-fA-F]{2}', f) for f in hex_fields):
            compat = bytes.fromhex(' '.join(hex_fields)).decode('ascii').rstrip('\x00').split('\x00')
        return dict(device=device, driver=driver['text'] if driver['available'] else '',
                    resources=resources, compatible=compat)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-boot', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', args.expected_boot):
        parser.error('--expected-boot must be a freshly read UUID')
    provenance = source_contract()  # Host failure happens before opening COM8.
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out = ROOT / 'results' / ('p36-display-readback-' + stamp)
    out.mkdir(exist_ok=False)
    report = dict(schema='rfsig.p36_display_readback.v1', status='reading',
                  stages=[], reads={}, checks={}, bindings=[], source=provenance,
                  expected_boot=args.expected_boot, read_only=True,
                  register_writes=False, sysfs_writes=False, physical_panel_confirmed=False,
                  physical_PCLK_measured=False, serial_closed=False,
                  scope='Software state and gated read-only ClockWiz status/config only.')

    def save():
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')

    board = None
    save()
    try:
        board = BoardConsole('COM8', report, save)
        board.port = AuditPort(board.port, out)
        board.shell()
        reader = Reader(board, report, save)
        identity = reader.capture('identity', 'uname -a')['text']
        if 'Zynq-Tronlong' not in identity:
            raise RuntimeError('wrong board identity; stopping')
        report['boot_id'] = board.value('/proc/sys/kernel/random/boot_id')
        report['tainted_before'] = board.value('/proc/sys/kernel/tainted')
        if report['boot_id'] != args.expected_boot or report['tainted_before'] != '0':
            raise RuntimeError('boot mismatch or tainted kernel; stopping')
        names = {}
        for path in reader.paths('iio_paths', '/sys/bus/iio/devices'):
            if re.search(r'/iio:device\d+$', path):
                item = reader.file(path + ':name', path + '/name')
                if item['available']:
                    if item['text'] in names:
                        raise RuntimeError('ambiguous duplicate IIO name')
                    names[item['text']] = path
        report['IIO_names'] = names
        if not RF_NAMES <= names.keys():
            raise RuntimeError('three expected RF names absent; stopping')
        if not reader.capture('fb0_device', 'test -c /dev/fb0')['available']:
            raise RuntimeError('merged framebuffer character device absent; stopping')
        report['identity_gates_passed'] = True
        first_up = reader.file('uptime_before', '/proc/uptime')
        reader.file('interrupts_before', '/proc/interrupts')
        for key, path in [
            ('fabric', '/sys/class/fpga_manager/fpga0/state'),
            ('clk_summary', '/sys/kernel/debug/clk/clk_summary'),
            ('pwm_debug', '/sys/kernel/debug/pwm'),
            ('current_clocksource', '/sys/devices/system/clocksource/clocksource0/current_clocksource'),
            ('available_clocksources', '/sys/devices/system/clocksource/clocksource0/available_clocksource'),
        ]:
            reader.file(key, path)
        for attr in ['name', 'virtual_size', 'stride', 'bits_per_pixel', 'modes',
                     'mode', 'blank', 'state', 'pan', 'rotate']:
            reader.file('fb0_' + attr, '/sys/class/graphics/fb0/' + attr)
        fb = report['reads']
        report['framebuffer_storage'] = framebuffer_storage(
            fb['fb0_virtual_size']['text'], fb['fb0_bits_per_pixel']['text'], fb['fb0_stride']['text'])
        report['checks']['fb_storage_accommodates_800x480_32bpp'] = report['framebuffer_storage'].get(
            'accommodates_800x480_32bpp')
        report['checks']['current_fb_mode_sysfs_800x480'] = bool(re.search(
            r'\b800x480(?:[pi-]|\b)', fb['fb0_mode']['text'])) if fb['fb0_mode']['available'] else None
        fbset = reader.capture('fbset_command', 'command -v fbset')
        if fbset['available'] and re.fullmatch(r'/[A-Za-z0-9_/.-]+', fbset['text'].strip()):
            # -s only reports current fb ioctl geometry; no geometry/value setters.
            reader.capture('fbset_readonly_geometry', 'fbset -fb /dev/fb0 -s')
        reader.path('/sys/class/graphics/fb0')
        reader.capture('fb0_device_driver', 'readlink "$p/device/driver"')
        for device in reader.paths('backlight_paths', '/sys/class/backlight'):
            for attr in ['type', 'brightness', 'actual_brightness', 'max_brightness', 'bl_power']:
                reader.file(device + ':' + attr, device + '/' + attr)
        devices = reader.paths('platform_device_paths', '/sys/bus/platform/devices')
        for device in devices:
            if re.search(r'43c10000|43c20000|43000000|ttc_pwm|backlight|xilinx_drm|drm_encoder', device):
                report['bindings'].append(reader.binding(device))
        for name in sorted(RF_NAMES):
            reader.path(names[name])
            reader.capture(name + ':driver', 'readlink "$p/device/driver"')
        clocks = {}
        try:
            clocks = parse_clocks(fb['clk_summary']['text'])
            report['clocks'] = clocks
        except ValueError as exc:
            report['clock_parse_error'] = str(exc)
        pixel = clocks.get('clk_out1', {})
        report['checks']['software_pixel_33MHz_enabled'] = (
            pixel.get('enable_count', 0) > 0 and pixel.get('prepare_count', 0) > 0 and
            abs(pixel.get('rate_hz', 0) - 33000000) <= 1000)
        report['pwm_state'] = pwm_state(fb['pwm_debug']['text'])
        for key in ['PWM2_requested_enabled_50us_nonzero_duty', 'PWM0_PWM1_not_requested']:
            report['checks'][key] = report['pwm_state'].get(key)
        wizard = [b for b in report['bindings']
                  if any(r[0] == 0x43C10000 for r in b['resources'])]
        gate = wizard_gate(wizard[0], clocks, fb['fabric']['text']) if len(wizard) == 1 else dict(
            allowed=False, reasons=['unique ClockWiz resource device not established'])
        report['ClockWiz_register_read_gate'] = gate
        if gate['allowed']:
            tool = reader.capture('devmem_command', 'command -v devmem')
            executable = tool['text'].strip()
            if tool['available'] and re.fullmatch(r'/[A-Za-z0-9_/.-]+', executable):
                registers = {}
                for key, address in REGISTERS.items():
                    item = reader.capture('ClockWiz_' + key, f'devmem 0x{address:08x} 32')
                    if item['available'] and re.fullmatch(r'0[xX][0-9a-fA-F]{1,8}', item['text']):
                        registers[key] = int(item['text'], 16)
                report['ClockWiz_registers'] = registers
                if set(registers) == set(REGISTERS):
                    report['ClockWiz_decode'] = decode_wizard(registers, clocks['fclk0']['rate_hz'], pixel.get('rate_hz'))
                    report['checks']['ClockWiz_LOCK'] = report['ClockWiz_decode']['locked']
                else:
                    report['ClockWiz_skip'] = 'one or more register reads unavailable/unrecognized; raw errors retained'
            else:
                report['ClockWiz_skip'] = 'devmem unavailable or tool path not established; no register read attempted'
        else:
            report['ClockWiz_skip'] = 'read gate not established; no register read attempted'
        reader.file('interrupts_after', '/proc/interrupts')
        last_up = reader.file('uptime_after', '/proc/uptime')
        if first_up['available'] and last_up['available']:
            delta = float(last_up['text'].split()[0]) - float(first_up['text'].split()[0])
            lower = last_up['host_begin'] - first_up['host_end']
            upper = last_up['host_end'] - first_up['host_begin']
            report['timer_observation'] = dict(board_uptime_delta_s=delta,
                host_delta_bracket_s=[lower, upper], tolerance_s=0.25,
                limitation='Monotonic UART observation only; timer jitter/IRQ latency not measured.')
            report['checks']['uptime_progress_matches_host_bracket'] = lower - .25 <= delta <= upper + .25
        report['boot_id_after'] = board.value('/proc/sys/kernel/random/boot_id')
        report['tainted_after'] = board.value('/proc/sys/kernel/tainted')
        report['checks']['same_boot_and_taint0_after'] = (
            report['boot_id_after'] == args.expected_boot and report['tainted_after'] == '0')
        reader.capture('kernel_tail', 'dmesg | tail -n 100', timeout=20)
        report['optional_reads_unavailable'] = [k for k, v in report['reads'].items() if not v['available']]
        report['status'] = 'read_only_evidence_collected'
        report['not_accepted_by_this_script'] = [
            'physical panel visible', 'measured external PCLK or backlight waveform',
            'timer jitter/latency', 'RF/display concurrency, signal quality, or sample continuity']
    except Exception as exc:
        report.update(status='stopped', error=repr(exc))
    finally:
        if board:
            board.close()
        report['serial_closed'] = True
        report['finished_utc'] = datetime.now(timezone.utc).isoformat()
        save()
        print(out)
        print(json.dumps(dict(status=report['status'], checks=report['checks'],
                              ClockWiz_skip=report.get('ClockWiz_skip')), indent=2))
    return 0 if report['status'] == 'read_only_evidence_collected' else 1


if __name__ == '__main__':
    raise SystemExit(main())
