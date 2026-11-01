"""Session-safe UART evidence and fresh identification; no RF/firmware writes."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import time
import uuid
import serial
from serial.tools import list_ports

ROOT = Path(__file__).resolve().parents[1]


class BoardConsole:
    def __init__(self, port, record, save):
        self.name, self.record, self.save = port, record, save
        self.port = serial.Serial(port=None, baudrate=115200, timeout=.1, write_timeout=3)
        self.port.dtr = False
        self.port.rts = False
        self.port.port = port
        self.port.open()

    def close(self):
        self.port.close()

    def read(self, seconds, pattern=None):
        raw = bytearray()
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            raw.extend(self.port.read(self.port.in_waiting or 1))
            if pattern and re.search(pattern, raw.decode('ascii', errors='replace'), re.M):
                break
        return raw.decode('ascii', errors='replace')

    def shell(self):
        passive = self.read(.5)
        self.port.write(b'\r')
        text = passive + self.read(2)
        self.record['stages'].append(dict(port=self.name, stage='wake', output=text))
        self.save()
        if re.search(r'login:\s*$', text):
            self.port.write(b'root\r')
            text = self.read(3)
            if re.search(r'Password:\s*$', text, re.I):
                # Existing board credential, never copied into experiment logs.
                self.port.write(b'analog\r')
                text = self.read(3)
            self.record['stages'].append(dict(port=self.name, stage='login_result', output=text))
            self.save()
        if not re.search(r'(?:^|\n)[^\r\n]*#\s*$', text):
            raise RuntimeError('root shell not established on ' + self.name)

    def command(self, command, timeout=8):
        if len(command) > 72 or '\n' in command or '\r' in command:
            raise ValueError('board command must be one line <=72 characters')
        token = '__P32_' + uuid.uuid4().hex[:8] + '__'
        self.port.write((command + '\recho ' + token + ':$?\r').encode('ascii'))
        text = self.read(timeout, r'^' + token + r':\d+\r?$')
        found = re.search(r'^' + token + r':(\d+)\r?$', text, re.M)
        rc = int(found[1]) if found else None
        self.record['stages'].append(dict(port=self.name, command=command,
            output=text, exit_code=rc, utc=datetime.now(timezone.utc).isoformat()))
        self.save()
        if rc != 0:
            raise RuntimeError(f'{self.name} command failed rc={rc}: {command}')
        return text

    def value(self, path):
        if not re.fullmatch(r'[A-Za-z0-9_./:$-]+', path):
            raise ValueError('unexpected attribute path')
        self.command('a=' + path)
        text = self.command('echo __VALUE__$(cat $a)__END__')
        values = re.findall(r'^__VALUE__(.*?)__END__\r?$', text, re.M)
        if len(values) != 1:
            raise RuntimeError('ambiguous attribute frame')
        return values[0]


def main():
    out = ROOT/'results'/datetime.now(timezone.utc).strftime('p32-preflight-%Y%m%dT%H%M%SZ')
    out.mkdir(exist_ok=False)
    record = dict(status='reading', stages=[], boards={}, read_only=True,
        firmware_writes=False, RF_attribute_writes=False,
        ports=[dict(port=p.device, description=p.description, hwid=p.hwid) for p in list_ports.comports()])
    def save():
        (out/'report.json').write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8')
    save()
    for port, expected in [('COM9', 'Linux pzp201'), ('COM8', 'Zynq-Tronlong')]:
        board = None
        try:
            board = BoardConsole(port, record, save)
            board.shell()
            identity = board.command('uname -a')
            if expected not in identity:
                raise RuntimeError('wrong board identity; no further commands')
            info = record['boards'][port] = dict(identity=identity,
                boot_id=board.value('/proc/sys/kernel/random/boot_id'),
                tainted=board.value('/proc/sys/kernel/tainted'))
            ps = board.command('ps' if port == 'COM9' else 'ps -ef')
            info['experiment_process_observed'] = any(re.search(r'arm-tx-source|p27-rx|arm-rx-capture|iio_readdev', line) for line in ps.splitlines())
            board.command('cat /proc/uptime')
            board.command('p=/sys/bus/iio/devices')
            names = board.command('for d in $p/iio:device*; do echo $d; cat $d/name; done')
            info['names'] = {n:p for p,n in re.findall(r'(/sys/bus/iio/devices/iio:device\d+)\r?\n([^\r\n]+)', names)}
            if port == 'COM8':
                info['mode'] = board.value('/etc/board-mode')
                info['fabric'] = board.value('/sys/class/fpga_manager/fpga0/state')
                installed = board.command('sha256sum /etc/rcS.d/S99board')
                digest = hashlib.sha256((ROOT/'board/boot/S99board').read_bytes()).hexdigest()
                info['guard_matches'] = digest in installed
                board.command('dmesg | tail -n 160')
                board.command('cat /proc/interrupts')
                board.command('cat /proc/iomem')
                ready = board.command('/etc/rcS.d/S99board --check-rf || true')
                info['rf_ready'] = bool(re.search(r'^RF_READY phy=', ready, re.M))
                for name in ['ad9361-phy','cf-ad9361-lpc','cf-ad9361-dds-core-lpc']:
                    if name not in info['names']:
                        raise RuntimeError('RF device missing: ' + name)
                board.command('cd ' + info['names']['ad9361-phy'])
                info['RX_attributes'] = {a:board.value(a) for a in [
                    'in_voltage_sampling_frequency', 'in_voltage_rf_bandwidth',
                    'out_altvoltage0_RX_LO_frequency', 'in_voltage0_gain_control_mode',
                    'in_voltage0_hardwaregain', 'in_voltage0_rf_port_select']}
                board.command('cd ' + info['names']['cf-ad9361-lpc'])
                info['buffer_enable'] = board.value('buffer/enable')
                info['scan_enable'] = [board.value(f'scan_elements/in_voltage{i}_en') for i in range(4)]
                if not info['guard_matches'] or info['tainted'] != '0':
                    raise RuntimeError('guard or kernel state unexpected')
            info['status'] = 'identified_current_boot'
        except Exception as exc:
            record['boards'].setdefault(port, {}).update(status='failed', error=repr(exc))
        finally:
            if board:
                board.close()
            save()
    record['serial_closed'] = True
    record['status'] = 'both_boards_identified' if all(v.get('status') == 'identified_current_boot' for v in record['boards'].values()) else 'incomplete'
    save()
    print(out)
    print(json.dumps({k:{a:b for a,b in v.items() if a not in ['identity','names']} for k,v in record['boards'].items()}, indent=2))
    return 0 if record['status'] == 'both_boards_identified' else 1


if __name__ == '__main__':
    raise SystemExit(main())
