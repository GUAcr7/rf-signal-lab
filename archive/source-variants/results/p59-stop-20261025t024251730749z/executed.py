"""Fixed, audited P59 status/RX-stop/RX-start/calibration entry.

No automatic RF transmit, reboot, PL reload or persistent configuration writes.
Each start preserves the previous RAM session and runs the accepted P56 binary.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'experiments')]
from serial.tools import list_ports
from rfsig.board_session import (WORK, boot_uuid, classify_rx, discover_ports,
                                one_json, require_rx_control, require_tx_off)
from p46_console import Console
from p35_once_merged_trial import AuditPort
from p46_preflight import parse_names
from p36_full_rx_run import RF_EXPECTED, CRITICAL_KERNEL


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_profile():
    # Read the accepted immutable checkpoint identity; do not rewrite its claims.
    active_path = ROOT / 'results/p58-active.json'
    active = json.loads(active_path.read_text('utf-8'))
    final_path = ROOT / active['report']
    if sha(final_path) != active['report_sha256']:
        raise ValueError('Accepted P58 report changed')
    final = json.loads(final_path.read_text('utf-8'))
    boot_path = ROOT / final['boot']
    boot = json.loads(boot_path.read_text('utf-8'))
    directory = boot['installed_directory']
    if not re.fullmatch(r'/etc/p43-\d{8}T\d{6}Z', directory):
        raise ValueError('Unexpected accepted profile directory')
    for name, wanted in boot['installed_files_sha256'].items():
        if sha(boot_path.parent / 'files' / name) != wanted:
            raise ValueError('Accepted profile snapshot changed: ' + name)
    return boot, {'accepted_boot_report': str(boot_path),
                  'accepted_boot_report_sha256': sha(boot_path),
                  'accepted_final_report_sha256': sha(final_path)}


class Controller:
    def __init__(self, action):
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        self.out = ROOT / 'results' / ('p59-' + action + '-' + stamp)
        self.out.mkdir()
        self.profile, provenance = load_profile()
        self.record = dict(status='checking', action=action, stages=[], boards={},
                           RF_transmissions=0, RF_attribute_writes=False,
                           PL_changes=False, reboots_issued=0,
                           persistent_file_writes=False, serial_closed=False,
                           created_utc=datetime.now(timezone.utc).isoformat(),
                           provenance=provenance)
        (self.out / 'executed.py').write_bytes(Path(__file__).read_bytes())
        self.record['ports'] = [dict(device=p.device, vid=p.vid, pid=p.pid,
                                     serial_number=p.serial_number, location=p.location,
                                     description=p.description)
                                for p in list_ports.comports()]
        self.save()
        self.ports = None

    def save(self):
        (self.out / 'report.json').write_text(
            json.dumps(self.record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    @contextmanager
    def board(self, role):
        b = None
        tty_saved = False
        folder = self.out / (role + '-' + uuid.uuid4().hex[:8])
        folder.mkdir()
        try:
            b = Console(self.ports[role], self.record, self.save)
            b.port = AuditPort(b.port, folder)
            b.shell()
            identity = b.command('uname -a')
            if ('Linux pzp201' if role == 'TX' else 'Zynq-Tronlong') not in identity:
                raise ValueError('Unexpected Linux identity on ' + role)
            b.command('p59_prompt=$PS1'); b.command('p59_tty=$(stty -g)')
            tty_saved = True
            b.command("PS1=''"); b.command('stty -echo')
            yield b, identity
        finally:
            if b:
                if tty_saved:
                    try:
                        b.command('stty "$p59_tty"'); b.command('PS1=$p59_prompt')
                    except Exception as error:
                        self.record.setdefault('TTY_restore_errors', []).append(repr(error))
                b.close()
            self.save()

    @staticmethod
    def optional(b, path):
        if not re.fullmatch(r'/[A-Za-z0-9_./-]+', path):
            raise ValueError('Unexpected read path')
        b.command('v=' + path)
        return b.command('if test -f $v;then cat $v;fi')

    @staticmethod
    def digest(b, path):
        b.command('v=' + path)
        matches = re.findall(r'^([0-9a-f]{64})\s+\S+\r?$', b.command('sha256sum $v'), re.M)
        if len(matches) != 1:
            raise ValueError('Ambiguous SHA: ' + path)
        return matches[0]

    def inspect(self, role, b, identity):
        info = dict(identity=identity, boot_id=boot_uuid(b.value('/proc/sys/kernel/random/boot_id')),
                    taint=b.value('/proc/sys/kernel/tainted'))
        b.command('ir=/sys/bus/iio/devices')
        names = parse_names(b.command('for n in $ir/iio:device*;do echo __D__$n:$(cat $n/name)__E__;done'))
        info['IIO_names'] = names
        b.command('cd ' + names['ad9361-phy'])
        attrs = (list(RF_EXPECTED) if role == 'RX' else
                 ['out_voltage_sampling_frequency', 'out_voltage_rf_bandwidth',
                  'out_altvoltage1_TX_LO_frequency', 'out_voltage0_hardwaregain',
                  'out_voltage0_rf_port_select'])
        info['RF'] = {key: b.value(key) for key in attrs}
        info['RX_buffer'] = b.value(names['cf-ad9361-lpc'] + '/buffer/enable')
        info['TX_buffer'] = b.value(names['cf-ad9361-dds-core-lpc'] + '/buffer/enable')
        info['kernel_tail'] = b.command('dmesg | tail -n 160')
        info['critical_kernel_fault'] = bool(re.search(CRITICAL_KERNEL, info['kernel_tail']))
        if role == 'TX':
            info['processes'] = b.command('ps')
            info['TX_process_observed'] = bool(re.search(r'arm-tx-source|\./guard --run', info['processes']))
            b.command('cd ' + names['cf-ad9361-dds-core-lpc'])
            def dds(suffix):
                output = b.command('for n in out_altvoltage*_' + suffix + ';do cat $n;done')
                values = [s.strip() for s in output.splitlines() if re.fullmatch(r'-?\d+(?:\.\d+)?\r?', s)]
                return ['0' if float(v) == 0 else v for v in values]
            info['DDS_raw'] = dds('raw'); info['DDS_scale'] = dds('scale')
            info['UART_devices'] = b.command('ls -l /dev/ttyPS*')
            info['UART_runtime'] = b.command('cat /proc/tty/driver/xuartps || true')
            info['root_mounts'] = b.command('cat /proc/mounts')
        else:
            info['RF_matches'] = info['RF'] == RF_EXPECTED
            info['RX_scans'] = [b.value(names['cf-ad9361-lpc'] + '/scan_elements/in_voltage' + str(i) + '_en') for i in range(4)]
            d = self.profile['installed_directory']
            info['profile_hashes'] = {name: self.digest(b, d + '/' + name)
                                      for name in self.profile['installed_files_sha256']}
            info['selected_wrapper_sha256'] = self.digest(b, '/etc/rcS.d/S99board')
            info['profile_verified'] = (info['profile_hashes'] == self.profile['installed_files_sha256']
                and info['selected_wrapper_sha256'] == self.profile['installed_files_sha256']['boot'])
            info['init_boot_marker'] = self.optional(b, '/run/p43-init-boot').strip()
            # Strip framing lines; optional scalar values use a distinct frame below.
            for key, path in [('init_boot_marker', '/run/p43-init-boot'), ('exit_code', WORK + '/exit'), ('owned_pid', WORK + '/pid')]:
                b.command('v=' + path)
                text = b.command('echo __S__$(cat $v 2>/dev/null)__E__')
                values = re.findall(r'^__S__(.*?)__E__\r?$', text, re.M)
                if len(values) != 1:
                    raise ValueError('Ambiguous optional scalar')
                info[key] = values[0] if values[0] else None
            info['owned_timeout_pid'] = int(info['owned_pid']) if str(info['owned_pid']).isdigit() else None
            info['owned_timeout_argv'] = []
            if info['owned_timeout_pid'] and info['owned_timeout_pid'] > 1:
                b.command('v=/proc/' + str(info['owned_timeout_pid']) + '/cmdline')
                text = b.command("if test -f $v;then tr '\\000' '\\n' <$v;fi")
                info['owned_timeout_argv'] = [s.rstrip('\r') for s in text.splitlines()
                    if s and not s.startswith('__P46_')]
            info['progress'] = one_json(self.optional(b, WORK + '/data/progress.json'), optional=True)
            info['AI'] = one_json(self.optional(b, WORK + '/data/ai.json'), optional=True)
            time.sleep(1)
            info['later_progress'] = one_json(self.optional(b, WORK + '/data/progress.json'), optional=True)
            info['progress_advancing'] = bool(info['progress'] and info['later_progress']
                and info['later_progress'].get('display_updates', 0) > info['progress'].get('display_updates', 0))
            info['session_state'] = classify_rx(info)
        if b.value('/proc/sys/kernel/random/boot_id') != info['boot_id']:
            raise ValueError('Boot changed during inspection')
        return info

    def status(self):
        self.ports = discover_ports(self.record['ports'])
        self.record['resolved_ports'] = self.ports
        self.save()
        errors = []
        for role in ('TX', 'RX'):
            try:
                with self.board(role) as (b, identity):
                    self.record['boards'][role] = self.inspect(role, b, identity)
            except Exception as error:
                self.record['boards'][role] = {'error': repr(error)}
                errors.append(role)
            self.save()
        if errors:
            raise ValueError('Could not identify/read: ' + ', '.join(errors))

    def action(self, action):
        self.status()
        tx, rx = self.record['boards']['TX'], self.record['boards']['RX']
        if action == 'status':
            return
        if action == 'source-off':
            if (tx['taint'] != '0' or tx['TX_buffer'] != '0'
                    or tx['TX_process_observed'] or tx['DDS_scale'] != ['0'] * 8):
                raise ValueError('Source-off requires idle TX with all DDS scales zero')
            with self.board('TX') as (b, identity):
                fresh = self.inspect('TX', b, identity)
                if (fresh['boot_id'] != tx['boot_id'] or fresh['taint'] != '0'
                        or fresh['TX_buffer'] != '0' or fresh['TX_process_observed']
                        or fresh['DDS_scale'] != ['0'] * 8):
                    raise ValueError('TX changed before zero-source selection')
                b.command('cd ' + fresh['IIO_names']['cf-ad9361-dds-core-lpc'])
                b.command('for n in out_altvoltage*_raw;do echo 0 >$n;done')
                self.record['DDS_zero_source_selected'] = True
                after = self.inspect('TX', b, identity)
                require_tx_off(after)
                if after['RF'] != fresh['RF']:
                    raise ValueError('RF attributes changed during zero-source selection')
                self.record['after_TX'] = after
                self.record['result'] = 'verified_idle_DDS_zero_source_not_absolute_RF_silence'
            return
        if action == 'stop' and rx['session_state'] == 'STOPPED':
            self.record['result'] = 'already_stopped_verified_idle'
            return
        if action == 'start' and rx['session_state'] == 'RUNNING':
            self.record['result'] = 'existing_running_session_reused_no_second_RX'
            return
        require_rx_control(rx, running=(action in ('stop', 'calibrate')))
        if action in ('start', 'calibrate'):
            require_tx_off(tx)
        with self.board('RX') as (b, identity):
            current = self.inspect('RX', b, identity)
            if current['boot_id'] != rx['boot_id']:
                raise ValueError('Boot changed since preflight')
            require_rx_control(current, running=(action in ('stop', 'calibrate')))
            b.command('j=' + self.profile['installed_directory'])
            b.command('w=' + WORK)
            if action == 'stop':
                b.command('sh $j/control stop', timeout=20)
            elif action == 'calibrate':
                # Recheck source-off immediately before requesting background.
                with self.board('TX') as (t, tx_identity):
                    fresh = self.inspect('TX', t, tx_identity)
                    if fresh['boot_id'] != tx['boot_id']:
                        raise ValueError('TX boot changed')
                    require_tx_off(fresh)
                    token = uuid.uuid4().hex
                    b.command('k=' + token); b.command('sh $j/control calibrate $k')
                    self.record['calibration_token'] = token
                time.sleep(3)
            elif action == 'start':
                summary = one_json(self.optional(b, WORK + '/data/summary.json'))
                if not all(summary.get(k) for k in ('buffer_released', 'context_released', 'worker_joined', 'RF_after_matches')) or summary.get('cleanup_unconfirmed'):
                    raise ValueError('Previous session cleanup not proven')
                previous = '/run/p59-prior-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
                b.command('r=' + previous); b.command('test ! -e $r')
                b.command('test -d $w'); b.command('test ! -L $w')
                b.command('mv $w $r'); self.record['preserved_previous_session'] = previous
                b.command('mkdir $w'); b.command('cp $j/monitor $w/monitor')
                b.command('cp $j/run $w/run'); b.command('chmod 755 $w/monitor')
                for name in ('monitor', 'run'):
                    if self.digest(b, WORK + '/' + name) != self.profile['installed_files_sha256'][name]:
                        raise ValueError('New RAM session bytes differ')
                b.command('sh $w/run </dev/null >/dev/null 2>&1 &')
                self.record['host_started_RX_only'] = True
                time.sleep(3)
            final = self.inspect('RX', b, identity)
            self.record['after_RX'] = final
            if action == 'stop':
                require_rx_control(final, running=False)
            else:
                require_rx_control(final, running=True)
                if not final['progress_advancing']:
                    raise ValueError('New/current RX progress did not advance')
                ai = final['AI']
                if action == 'start' and (ai['state'] != 'CALIBRATION_REQUIRED' or ai['ready'] or ai['accepted_class'] != -1 or ai['calibration_token']):
                    raise ValueError('New session reused old calibration')
                if action == 'calibrate' and (ai['state'] != 'WAIT_PILOT' or ai['calibration_token'] != self.record['calibration_token']):
                    raise ValueError('Fresh background calibration not waiting for pilot')
            self.record['result'] = 'verified_' + action


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('action', choices=('status', 'start', 'stop', 'calibrate', 'source-off'), nargs='?', default='status')
    args = ap.parse_args()
    c = None
    try:
        c = Controller(args.action)
        print(c.out, flush=True)
        c.action(args.action)
        c.record['status'] = 'passed_P59_' + args.action
    except Exception as error:
        if c:
            c.record.update(status='failed_or_unconfirmed_P59_' + args.action, error=repr(error))
        else:
            print(repr(error), file=sys.stderr)
        return 1
    finally:
        if c:
            c.record['serial_closed'] = True
            c.save()
            print(c.record['status'], flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
